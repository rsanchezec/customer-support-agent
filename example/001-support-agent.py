# Antes de ejecutar este ejemplo hay que instalar:
#     uv pip install agent-framework>=1.8.0 azure-ai-projects>=2.2.0 \
#                     azure-identity openai python-dotenv
# (Estas dos primeras líneas son solo documentación para el lector, no se ejecutan.)

# warnings: módulo estándar. Filtra los ExperimentalWarning de agent_framework.
import warnings
# Silencia los avisos de "feature experimental" que el SDK escupe al importarse.
# Importante: el filterwarnings debe ir ANTES de los import de agent_framework.
warnings.filterwarnings("ignore", message=r"\[(SKILLS|HARNESS)\]")

# os: para leer variables de entorno.
import os
# asyncio: motor asíncrono. FoundryAgent.run() es awaitable, así que lo necesitamos.
import asyncio
# dotenv: vuelca el .env en os.environ.
from dotenv import load_dotenv

# AIProjectClient (versión ASÍNCRONA): cliente del SDK azure-ai-projects.
# Importamos desde .aio porque vamos a usarlo dentro de un `async with`
# y el cliente sync (azure.ai.projects.AIProjectClient) NO soporta el
# protocolo de context manager asíncrono.
from azure.ai.projects.aio import AIProjectClient
# AgentVersionDetails: tipo de retorno de get_version, lo usamos como
# anotación de salida de get_existing_agent().
from azure.ai.projects.models import AgentVersionDetails
# AzureCliCredential (versión asíncrona): usa el token de `az login`.
# Es la versión async de DefaultAzureCredential, necesaria para los await.
from azure.identity.aio import AzureCliCredential
# FoundryAgent: la clase MODERNA de agent_framework para invocar un agente
# ya desplegado en Foundry. Sustituye al patrón responses.create + extra_body
# que usaba la versión antigua; aquí la llamada al modelo queda mucho más limpia.
from agent_framework.foundry import FoundryAgent

# Carga el .env. override=True machaca variables previas del proceso.
load_dotenv(override=True)

# Variables de entorno. Mismas claves que ya tienes definidas en el .env.
project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
agent_name = os.getenv("AZURE_AI_AGENT_NAME", "customer-support-agent")
# Versión concreta del agente que queremos invocar. Por defecto "1" (la primera
# publicada en Foundry). Si subes el agente a una nueva versión, cámbialo aquí
# o define AGENT_VERSION en el .env.
agent_version = os.getenv("AGENT_VERSION", "1")

# Prompt de prueba: simulamos la consulta de un cliente insatisfecho por un
# cobro duplicado. El agente de soporte ya tiene en su system prompt las
# instrucciones de cómo responder (empatía, política de devoluciones, etc.);
# desde el cliente solo le mandamos la consulta del usuario.
CUSTOMER_QUERY = (
    "¿Qué debo hacer si se enciende la luz de advertencia del sistema de frenos?"   
)


# ----------------------------------------------------------------------
# Función 1: RECUPERAR el agente ya desplegado en Foundry
# ----------------------------------------------------------------------
# Aislada en su propia corrutina para:
#   1. Responsabilidad única: solo se ocupa de localizar el agente en el
#      proyecto (no de crearlo — eso lo haría otro script).
#   2. Testabilidad: se puede invocar desde tests con un project_client mock.
#   3. Reusabilidad: otro script podría llamarla para resolver un agente
#      cualquiera y luego operar con él.
#   4. Claridad: main() queda como un índice legible de lo que hace el script.
async def get_existing_agent(
    project_client: AIProjectClient,   # cliente del proyecto (gestionado por main)
    agent_name: str,                   # nombre lógico del agente en Foundry
    agent_version: str,                # versión concreta que queremos invocar
) -> AgentVersionDetails:
    # `agents` es el sub-cliente de AIProjectClient para gestión.
    # get_version() devuelve los metadatos de UNA versión concreta del agente:
    #   - .name  → el nombre lógico.
    #   - .version → el identificador de la versión (p. ej. "1", "2").
    # En el cliente async (azure.ai.projects.aio) devuelve una corutina,
    # por eso necesitamos el `await`. Si no lo awaitamos, lo único que
    # obtenemos es un objeto coroutine sin atributos.
    return await project_client.agents.get_version(
        agent_name=agent_name,             # nombre lógico del agente
        agent_version=agent_version,       # versión concreta (p. ej. "1")
    )


# ----------------------------------------------------------------------
# Función 2: INVOCAR al agente con el SDK MODERNO (agent_framework)
# ----------------------------------------------------------------------
# Aislada en su propia corrutina por las mismas razones que la función 1.
# Recibe el project_client y el agent_version ya resuelto, de modo que
# se puede reutilizar con agentes obtenidos por otros medios.
async def invoke_agent(
    project_client: AIProjectClient,   # cliente del proyecto (gestionado por main)
    agent_name: str,                   # nombre del agente a invocar
    agent_version: str,                # versión concreta (1, 2…)
    query: str,                        # mensaje del usuario / cliente
) -> str:
    # FoundryAgent es la pieza "nueva": envuelve internamente un
    # RawFoundryAgentChatClient que sabe hablar con la versión concreta
    # del agente en Foundry. Tú solo le das el name + version.
    agent = FoundryAgent(
        project_client=project_client,     # reusa el cliente del proyecto
        agent_name=agent_name,             # nombre del agente
        agent_version=agent_version,       # versión concreta (1, 2…)
        # Pasándole project_client + agent_name + agent_version hace la
        # llamada server-side apuntando al agente PERSISTENTE en Foundry.
        # Las instrucciones de sistema ya están en el agente, NO se
        # mandan en cada request (a diferencia del patrón de FoundryChatClient).
    )

    # .run() es awaitable y devuelve un AgentResponse con .text.
    result = await agent.run(query)
    # Devolvemos solo el texto final; main() se encarga de imprimirlo
    # (o de hacer lo que quiera con él: loggear, guardar en BD, etc.).
    return result.text


# ----------------------------------------------------------------------
# Función 3 (orquestadora): main()
# ----------------------------------------------------------------------
# Responsabilidad única: gestionar el ciclo de vida de los recursos
# (credencial + project_client) y encadenar las dos corrutinas de arriba.
# NO contiene lógica de recuperación ni de invocación: solo las llama.
async def main():
    # Bloque `async with` anidado: al salir cierra en orden inverso
    # (1) el project_client, (2) la credencial. Es la forma recomendada
    # de manejar recursos asíncronos en Python: garantiza liberación
    # incluso si algo lanza una excepción.
    async with (
        # Credencial async a partir de `az login`. Cierra su transport al salir.
        AzureCliCredential() as credential,
        # Cliente del proyecto. Como es la versión `.aio`, sí soporta
        # `async with`. Lo creamos UNA vez y lo compartimos con las dos
        # funciones siguientes, evitando abrir dos conexiones HTTP.
        AIProjectClient(
            endpoint=project_endpoint,         # URL del proyecto de Foundry
            credential=credential,             # reusa la credencial async
        ) as project_client,
    ):
        # ------------------------------------------------------------------
        # PASO 1: recuperar el agente ya desplegado en Foundry
        # ------------------------------------------------------------------
        # Llamamos a la función 1. Recibe el nombre + versión y devuelve un
        # AgentVersionDetails con .name y .version poblados.
        resolved = await get_existing_agent(
            project_client=project_client,         # reusa el cliente del async with
            agent_name=agent_name,                 # del .env / default
            agent_version=agent_version,           # del .env / default
        )

        # Imprime los identificadores del agente recuperado.
        # .name y .version son lo que luego pasamos a invoke_agent.
        print(
            f"Agente recuperado: name={resolved.name!r} "
            f"version={resolved.version!r}"
        )

        # ------------------------------------------------------------------
        # PASO 2: invocar al agente con la consulta del cliente
        # ------------------------------------------------------------------
        # Llamamos a la función 2. Le pasamos la versión resuelta en el
        # paso 1 para garantizar que invocamos exactamente la versión que
        # acabamos de localizar (no una que pueda haber cambiado entre
        # ambas llamadas).
        response_text = await invoke_agent(
            project_client=project_client,         # reusa el mismo cliente
            agent_name=resolved.name,              # nombre del agente recuperado
            agent_version=resolved.version,        # versión concreta
            query=CUSTOMER_QUERY,                  # constante arriba del archivo
        )

        # Imprime la respuesta del modelo. Aquí podría guardarse en BD,
        # enviarse por correo, etc. — la función 2 devuelve solo el texto.
        print(f"Response output: {response_text}")


# Bloque estándar: ejecuta main() solo si el archivo se lanza como script.
if __name__ == "__main__":
    # asyncio.run monta el event loop, corre la corrutina y lo cierra.
    asyncio.run(main())
