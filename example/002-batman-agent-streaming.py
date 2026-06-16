# Antes de ejecutar este ejemplo hay que instalar:
#     uv pip install agent-framework>=1.8.0 azure-ai-projects>=2.2.0 \
#                     azure-identity openai python-dotenv
# (Estas dos primeras líneas son solo documentación para el lector, no se ejecutan.)
#
# Variante "streaming" de 001-batman-agent.py. La diferencia: aquí cada
# turno imprime la respuesta token a token, en tiempo real, conforme el
# modelo los va generando (efecto "máquina de escribir"), en vez de esperar
# a que termine la respuesta completa y volcarla de golpe.

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
# Sigue siendo la única forma soportada de PERSISTIR un agente en Foundry
# (crear/versional). El SDK nuevo (agent_framework) NO expone create_agent:
# delega en este. Importamos desde .aio porque vamos a usarlo dentro de
# un `async with` y el cliente sync (azure.ai.projects.AIProjectClient) NO
# soporta el protocolo de context manager asíncrono.
from azure.ai.projects.aio import AIProjectClient
# PromptAgentDefinition: subtipo de AgentDefinition que define un agente
# "basado en prompt de sistema + modelo" — el caso típico.
from azure.ai.projects.models import PromptAgentDefinition
# AgentVersionDetails: tipo de retorno de create_version, lo usamos como
# anotación de salida de create_or_get_agent().
from azure.ai.projects.models import AgentVersionDetails
# AzureCliCredential (versión asíncrona): usa el token de `az login`.
# Es la versión async de DefaultAzureCredential, necesaria para los await.
from azure.identity.aio import AzureCliCredential
# FoundryAgent: la clase MODERNA de agent_framework para invocar un agente
# ya desplegado en Foundry. Aquí la llamada al modelo queda mucho más limpia
# y se integra con middleware, telemetría, etc.
from agent_framework.foundry import FoundryAgent

# Carga el .env. override=True machaca variables previas del proceso.
load_dotenv(override=True)

# Variables de entorno. Mismas claves que en el resto de la carpeta
# 001-first-agent y que en el .env de este directorio.
project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
# Nombre del agente. Aquí lo fijamos a "batman-agent".
# Si en el .env defines AZURE_AI_AGENT_NAME, se usará ese valor en su lugar.
agent_name = os.getenv("AZURE_AI_AGENT_NAME", "batman-agent")
# Nombre del deployment del modelo en Foundry (p. ej. "gpt-4o", "gpt-5-mini").
# También con valor por defecto por si el .env no lo trae.
model = os.getenv("FOUNDRY_MODEL", "gpt-5-mini")

# Instrucciones de sistema del agente: le pedimos que responda SIEMPRE
# en personaje como Batman, el Caballero Oscuro de Ciudad Gótica.
INSTRUCTIONS = (
    "Eres Batman, el Caballero Oscuro de Ciudad Gótica. "
    "Responde SIEMPRE en personaje, tal como lo haría Batman: "
    "serio, estratégico, con sentido de la justicia y sin revelar "
    "tu identidad secreta. Puedes hacer referencias a tu batcueva, "
    "a tus aliados (Robin, Alfred, Comisionada Gordon) y a tus "
    "archienemigos (Joker, Pingüino, Acertijo, Dos Caras)."
)
# Descripción libre, útil en el portal de Foundry.
DESCRIPTION = "Agente que responde como Batman, el Caballero Oscuro"


# ----------------------------------------------------------------------
# Función 1: CREAR / VERSIONAR el agente en Foundry
# ----------------------------------------------------------------------
# Aislada en su propia corrutina para:
#   1. Responsabilidad única: solo se ocupa de la persistencia del agente.
#   2. Testabilidad: se puede invocar desde tests con un project_client mock.
#   3. Reusabilidad: otro script podría llamarla para crear otros agentes.
#   4. Claridad: main() queda como un índice legible de lo que hace el script.
async def create_or_get_agent(
    project_client: AIProjectClient,   # cliente del proyecto (gestionado por main)
    agent_name: str,                   # nombre lógico del agente en Foundry
    model: str,                        # deployment del modelo (p. ej. "gpt-5-mini")
    instructions: str,                 # prompt de sistema del agente
    description: str,                  # descripción libre para el portal
) -> AgentVersionDetails:
    # `agents` es el sub-cliente de AIProjectClient para gestión.
    # create_version() registra una nueva versión:
    #   - Si el agente NO existe, lo crea como v1.
    #   - Si YA existe y el contenido es idéntico, devuelve la versión
    #     existente (dedup en servidor, no incrementa contador).
    #   - Si YA existe y el contenido cambió, crea v2, v3...
    # En el cliente async (azure.ai.projects.aio) devuelve una corutina,
    # por eso necesitamos el `await`. Si no lo esperamos, lo único que
    # obtenemos es un objeto coroutine sin atributos.
    return await project_client.agents.create_version(
        agent_name=agent_name,             # nombre lógico del agente
        # Definición PromptAgent = instrucciones + modelo.
        definition=PromptAgentDefinition(
            model=model,                   # deployment del modelo
            # Instrucciones de sistema persistentes: viven en Foundry,
            # no en el código cliente (a diferencia de FoundryChatClient).
            instructions=instructions,
        ),
        # Descripción libre, útil en el portal de Foundry.
        description=description,
    )


# ----------------------------------------------------------------------
# Función 2: CHAT multi-turno con el agente (versión STREAMING)
# ----------------------------------------------------------------------
# La estructura es idéntica a la versión no-streaming, pero la llamada
# a `agent.run()` se hace con `stream=True` y se consume el resultado
# como un async iterable de `AgentResponseUpdate` para imprimir cada
# token según va llegando.
async def chat_with_batman(agent: FoundryAgent) -> None:
    # Crea una AgentSession NUEVA para esta sesión de chat. NO confundir
    # con `get_new_thread()` (esa API no existe en esta versión del SDK;
    # el método canónico es `create_session()` heredado de BaseAgent).
    session = agent.create_session()

    # Banner inicial. "Caballero Oscuro" es un guiño a las instrucciones.
    print("\n--- Chat con Batman (streaming) ---")
    print("Escribe 'exit' o 'quit' para salir.\n")

    # Bucle REPL clásico. Palabras de salida: "exit" o "quit".
    while True:
        # input() es síncrono y BLOQUEA el event loop. Como solo lanzamos
        # un único turno de chat a la vez, en la práctica no se nota, pero
        # en una app real habría que usar `asyncio.to_thread(input, ...)` o
        # leer desde un socket.
        user_input = input("Tú: ")
        # Normaliza a minúsculas para comparar las palabras de salida
        # sin importar cómo las escriba el usuario.
        if user_input.lower().strip() in ("exit", "quit"):
            print("Batman: Hasta otra, ciudadano. Gotham duerme mejor contigo.")
            break

        # ----------------------------------------------------------------
        # AQUÍ ESTÁ LA DIFERENCIA CLAVE vs la versión no-streaming:
        # ----------------------------------------------------------------
        # 1. Usamos `stream=True` en la llamada.
        # 2. NO ponemos `await` delante: cuando stream=True, run() devuelve
        #    directamente un `ResponseStream[AgentResponseUpdate, ...]`,
        #    que es un AsyncIterable — NO una corutina. Un `await` aquí
        #    provocaría `TypeError: object ResponseStream can't be used
        #    in 'await' expression`.
        # 3. El parámetro `session=session` se sigue pasando igual: el
        #    streaming path mantiene la sesión multi-turno automáticamente
        #    (vía el hook _propagate_conversation_id).
        # 4. La Responses API de Foundry con stream=True va emitiendo
        #    eventos de tipo "response.output_text.delta" que el cliente
        #    OpenAI del SDK agrupa en `AgentResponseUpdate` chunks.
        stream = agent.run(user_input, stream=True, session=session)

        # Imprime el prefijo "Batman: " UNA sola vez, sin newline y con
        # flush para que el usuario vea inmediatamente que el turno arrancó
        # y luego verá las palabras brotando una a una.
        print("Batman: ", end="", flush=True)

        # Itera el stream. Cada `update` es un `AgentResponseUpdate`:
        # - `update.text` es el delta de texto de ESE chunk (puede ser ""
        #   para eventos que no son texto, p. ej. function-call deltas).
        # - `end=""` evita que se meta un newline entre chunks.
        # - `flush=True` fuerza a que cada token se escriba en la terminal
        #   en el momento, no en el flush buffer de Python.
        async for update in stream:
            print(update.text, end="", flush=True)

        # Salto de línea final una vez consumido el stream entero.
        print()


# ----------------------------------------------------------------------
# Función 3 (orquestadora): main()
# ----------------------------------------------------------------------
# Responsabilidad única: gestionar el ciclo de vida de los recursos
# (credencial + project_client) y encadenar las dos corrutinas de arriba.
# NO contiene lógica de creación ni de chat: solo las llama.
async def main():
    # Bloque `async with` anidado: al salir cierra en orden inverso
    # (1) el project_client, (2) la credencial. Es la forma recomendada
    # de manejar recursos asíncronos en Python: garantiza liberación
    # incluso si algo lanza una excepción.
    async with (
        # Credencial async a partir de `az login`. Cierra su transport al salir.
        AzureCliCredential() as credential,
        # Cliente del proyecto. Como es la versión `.aio`, sí soporta
        # `async with`. Lo creamos UNA vez y lo compartimos con todo lo
        # que viene después, evitando abrir dos conexiones HTTP.
        AIProjectClient(
            endpoint=project_endpoint,         # URL del proyecto de Foundry
            credential=credential,             # reusa la credencial async
        ) as project_client,
    ):
        # ------------------------------------------------------------------
        # PASO 1: crear/recuperar el agente en Foundry
        # ------------------------------------------------------------------
        # Llamamos a la función 1. Recibe los datos y devuelve un
        # AgentVersionDetails con .name y .version poblados.
        agent_version = await create_or_get_agent(
            project_client=project_client,         # reusa el cliente del async with
            agent_name=agent_name,                 # del .env / default
            model=model,                           # del .env / default
            instructions=INSTRUCTIONS,             # constante local
            description=DESCRIPTION,               # constante local
        )

        # Imprime los identificadores del agente recién creado/recuperado.
        # .name y .version son lo que luego pasamos a FoundryAgent.
        print(
            f"Agente creado: name={agent_version.name!r} "
            f"version={agent_version.version!r}"
        )

        # ------------------------------------------------------------------
        # PASO 2: invocar al agente con el SDK MODERNO (agent_framework)
        # ------------------------------------------------------------------
        # FoundryAgent es la pieza "nueva": envuelve internamente un
        # RawFoundryAgentChatClient que sabe hablar con la versión concreta
        # del agente en Foundry. Tú solo le das el name+version.
        agent = FoundryAgent(
            project_client=project_client,     # reusa el cliente del async with
            agent_name=agent_version.name,     # nombre del agente
            agent_version=agent_version.version,  # versión concreta (v1, v2…)
            # Si FoundryAgent se construyera SIN project_client, usaría
            # internamente FoundryChatClient y las instrucciones se mandarían
            # en cada request como system prompt. PASÁNDOLE project_client +
            # agent_name + agent_version, en cambio, hace la llamada
            # server-side apuntando al agente PERSISTENTE en Foundry.
        )

        # ------------------------------------------------------------------
        # PASO 3: abrir el chat multi-turno en modo streaming
        # ------------------------------------------------------------------
        # Bloque `async with` alrededor de FoundryAgent: al salir cierra
        # limpiamente el cliente HTTP subyacente (cliente conversacional).
        async with agent:
            # Llamamos a la función 2. Se queda dentro hasta que el
            # usuario escribe "exit" o "quit".
            await chat_with_batman(agent)


# Bloque estándar: ejecuta main() solo si el archivo se lanza como script.
if __name__ == "__main__":
    # asyncio.run monta el event loop, corre la corrutina y lo cierra.
    asyncio.run(main())
