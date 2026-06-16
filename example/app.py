# Antes de ejecutar este ejemplo hay que instalar:
#     uv pip install agent-framework>=1.8.0 azure-ai-projects>=2.2.0 \
#                     azure-identity openai streamlit python-dotenv
# (Estas dos primeras líneas son solo documentación para el lector, no se ejecutan.)

# warnings: módulo estándar. Filtra los ExperimentalWarning de agent_framework.
import warnings
# Silencia los avisos de "feature experimental" que el SDK escupe al importarse.
# Importante: el filterwarnings debe ir ANTES de los import de agent_framework.
warnings.filterwarnings("ignore", message=r"\[(SKILLS|HARNESS)\]")

# os: para leer variables de entorno.
import os
# asyncio: motor asíncrono. FoundryAgent.run_stream() es un async generator.
import asyncio
# dotenv: vuelca el .env en os.environ.
from dotenv import load_dotenv
# streamlit: UI web síncrona. Haremos un bridge async->sync para hacer streaming.
import streamlit as st

# AIProjectClient (versión ASÍNCRONA): cliente del SDK azure-ai-projects.
# Importamos desde .aio porque vamos a usarlo dentro de un `async with`
# y el cliente sync (azure.ai.projects.AIProjectClient) NO soporta el
# protocolo de context manager asíncrono.
from azure.ai.projects.aio import AIProjectClient
# AgentVersionDetails: tipo de retorno de get_version, lo usamos como
# anotación de salida de resolve_agent().
from azure.ai.projects.models import AgentVersionDetails
# DefaultAzureCredential (versión SÍNCRONA): la usamos SOLO para la credencial
# cacheable. AIProjectClient async acepta credenciales sync y las envuelve
# internamente. La ventaja es que sync = trivial de cachear con
# @st.cache_resource (sin ciclo de vida async que gestionar).
# (Antes usábamos AzureCliCredential async, pero su ciclo de vida complica
# el cacheo — al ser sync, evitamos todo el problema.)
from azure.identity import DefaultAzureCredential
# FoundryAgent: la clase MODERNA de agent_framework para invocar un agente
# ya desplegado en Foundry. .run_stream() es lo que nos da los chunks
# incrementales que pintamos en pantalla mientras el modelo genera.
from agent_framework.foundry import FoundryAgent


# -----------------------------
# Streamlit setup
# -----------------------------
st.set_page_config(page_title="Support Agent", page_icon="💬", layout="centered")
st.title("💬 Customer Support Agent (Foundry)")


# -----------------------------
# Load env (.env optional)
# -----------------------------
load_dotenv(override=True)


PROJECT_ENDPOINT = os.environ.get("FOUNDRY_PROJECT_ENDPOINT") or os.getenv("AZURE_AI_PROJECT_ENDPOINT")
AGENT_NAME = os.getenv("AZURE_AI_AGENT_NAME") or os.getenv("AZURE_EXISTING_AGENT_NAME") or os.getenv("AZURE_EXISTING_AGENT_ID")
# Versión concreta del agente que queremos invocar.
# - Si defines AGENT_VERSION en el .env (p. ej. AGENT_VERSION=3), se usa ESA.
# - Si NO la defines, devolvemos None y resolve_agent hace auto-detect de la
#   última versión publicada. NUNCA ponemos default "1" aquí: si lo pusiéramos,
#   la rama de auto-detect nunca se ejecutaría (porque "1" es truthy).
AGENT_VERSION = os.getenv("AGENT_VERSION") or None


# IMPORTANT: if someone accidentally set AGENT_NAME to "customer-support-agent:2"
# normalize it back to the real name by stripping anything after ":".
if AGENT_NAME and ":" in AGENT_NAME:
   AGENT_NAME = AGENT_NAME.split(":")[0]


if not PROJECT_ENDPOINT:
   st.error("Missing FOUNDRY_PROJECT_ENDPOINT (or AZURE_AI_PROJECT_ENDPOINT).")
   st.stop()


if not AGENT_NAME:
   st.error("Missing AZURE_AI_AGENT_NAME (recommended). Set it to your agent name, e.g. supportTriangleAgent.")
   st.stop()


# -----------------------------
# Azure clients
# -----------------------------
# Cacheamos la CREDENCIAL (no el cliente) por dos motivos:
#   1) La autenticación es la parte CARA del setup por turno: cada vez
#      que creas una credencial nueva, internamente puede tener que ir
#      a Azure AD a por un token. Reutilizar la misma credencial entre
#      turnos aprovecha la caché de tokens interna del SDK.
#   2) Usar la versión SÍNCRONA (DefaultAzureCredential de azure.identity,
#      NO de azure.identity.aio) es trivial de cachear con
#      @st.cache_resource porque NO tiene ciclo de vida async que
#      gestionar. El AIProjectClient async la envuelve internamente
#      cuando la recibe en su constructor.
#
# NO cacheamos el AIProjectClient (como sugería la captura inicial)
# porque su ciclo de vida depende del `async with`: __aenter__ monta
# el httpx.AsyncClient interno y __aexit__ lo cierra. Si lo cacheáramos
# con @st.cache_resource y luego lo usáramos FUERA de un async with,
# el transport no se inicializa correctamente y fallaría al hacer
# la primera petición HTTP. Mantenemos el patrón `async with` por
# llamada: es la forma correcta y el handshake HTTP es barato
# (httpx mantiene el pool de conexiones internamente).
@st.cache_resource
def get_cached_credential():
   """Credencial SYNC cacheada en Streamlit. Se crea UNA vez por sesión."""
   return DefaultAzureCredential()


# NO creamos el project_client en cache_resource: el cliente async está pensado
# para vivir dentro de un `async with` por invocación. Lo que sí cacheamos es
# la corutina de resolución del agente (name + version) que solo necesitamos
# resolver una vez por (endpoint, agent_name, version) y reutilizar entre
# reruns de Streamlit.
@st.cache_resource
def resolve_agent(
   project_endpoint: str,
   agent_name: str,
   agent_version: str | None,    # None → auto-detectar la última versión
) -> AgentVersionDetails:
   """Resuelve el agente (name + version) en Foundry. Se cachea entre reruns.

   Comportamiento:
     - Si `agent_version` viene con valor (de la env var AGENT_VERSION),
       resuelve ESA versión concreta.
     - Si viene None (AGENT_VERSION no definida en el .env), lista TODAS
       las versiones publicadas del agente y se queda con la más reciente.
       Esto evita quedarte desfasado cuando publicas una nueva versión
       y olvidas actualizar el .env.
   """

   async def _resolve() -> AgentVersionDetails:
      # Bloque `async with` anidado: al salir cierra en orden inverso
      # (1) el project_client, (2) la credencial. Es la forma recomendada
      # de manejar recursos asíncronos en Python: garantiza liberación
      # incluso si algo lanza una excepción.
      async with (
         # Cliente del proyecto. Como es la versión `.aio`, sí soporta
         # `async with`. Lo creamos UNA vez y lo compartimos con la corutina.
         # La credencial es la SYNC cacheada: el SDK async la envuelve
         # internamente para pedir tokens desde su event loop.
         AIProjectClient(
            endpoint=project_endpoint,         # URL del proyecto de Foundry
            credential=get_cached_credential(),  # sync, cacheada
         ) as project_client,
      ):
         # `agents` es el sub-cliente de AIProjectClient para gestión.
         #
         # Caso 1: el usuario fijó AGENT_VERSION en el .env → úsala tal cual.
         if agent_version:
            # get_version() devuelve los metadatos de UNA versión concreta:
            #   - .name  → el nombre lógico.
            #   - .version → el identificador de la versión (p. ej. "3").
            return await project_client.agents.get_version(
               agent_name=agent_name,          # nombre lógico del agente
               agent_version=agent_version,    # versión concreta (p. ej. "3")
            )

         # Caso 2: AGENT_VERSION NO fijada → auto-detectar la última publicada.
         # list_versions() devuelve un AsyncIterable[AgentVersionDetails] con
         # TODAS las versiones del agente. Las recolectamos en una lista.
         versions = []
         async for v in project_client.agents.list_versions(agent_name=agent_name):
            versions.append(v)

         if not versions:
            # Sin versiones no podemos hacer nada. Damos un mensaje claro
            # para que el usuario sepa qué arreglar.
            raise RuntimeError(
               f"No versions found for agent '{agent_name}' in Foundry. "
               f"Publish a version first, or set AGENT_VERSION in your .env."
            )

         # Nos quedamos con la versión más alta. Para versiones numéricas
         # ("1", "2", "10") comparamos como int — si no se puede (semver
         # tipo "1.0.0", etc.) caemos a string. La tupla (0, ...) / (1, ...)
         # hace que las numéricas tengan prioridad sobre las no-numéricas
         # en caso de mezcla.
         def _version_key(v):
            try:
               return (0, int(v.version))
            except (ValueError, TypeError):
               return (1, str(v.version))

         latest = max(versions, key=_version_key)
         return latest

   # asyncio.run monta el event loop, corre la corrutina y lo cierra.
   return asyncio.run(_resolve())


def run_agent_stream(
   project_endpoint: str,
   agent_name: str,
   agent_version: str,
   query: str,
):
   """Generador SÍNCRONO que produce los chunks de texto del agente en orden.

   Estrategia de DOS NIVELES porque en esta versión de MAF `FoundryAgent`
   NO expone `run_stream()` (a pesar de que `ChatClientAgent` base sí lo
   declara). Por eso:

     1) Si la instancia TIENE `run_stream`, lo usamos (streaming real,
        incremental token a token desde el modelo).
     2) Si NO lo tiene (o falla con TypeError/AttributeError por firma
        incompatible), hacemos FALLBACK a `agent.run()` (no-streaming)
        y SIMULAMOS el efecto visual dividiendo la respuesta completa
        en palabras y emitiéndolas con un pequeño delay. Visualmente
        es casi indistinguible del streaming real para el usuario.

   El puente async->sync (event loop dedicado + run_until_complete sobre
   `__anext__`) es necesario porque Streamlit ejecuta callbacks de forma
   síncrona pero `run_stream()` y `run()` son awaitables / async generators.
   """

   async def _stream():
      # Separamos el ciclo de vida del project_client por llamada: lo abrimos
      # aquí, lo usamos durante todo el streaming, y lo cerramos al salir del
      # `async with`. Importante que el `async with` envuelva al `async for`,
      # NO al revés: si lo cerráramos antes, el agente dejaría de poder emitir
      # chunks a mitad del stream.
      #
      # La CREDENCIAL es la sync cacheada (get_cached_credential()): evitamos
      # re-autenticarnos en cada turno. El SDK async la envuelve internamente.
      async with (
         AIProjectClient(
            endpoint=project_endpoint,         # URL del proyecto de Foundry
            credential=get_cached_credential(),  # sync, cacheada por sesión
         ) as project_client,
      ):
         # FoundryAgent es la pieza "nueva": envuelve internamente un
         # RawFoundryAgentChatClient que sabe hablar con la versión concreta
         # del agente en Foundry. Tú solo le das el name + version.
         agent = FoundryAgent(
            project_client=project_client,     # reusa el cliente del proyecto
            agent_name=agent_name,             # nombre del agente
            agent_version=agent_version,       # versión concreta (1, 2…)
         )

         # --- Estrategia 1: streaming real ---------------------------------
         # hasattr() es nuestra forma de detectar en runtime si esta build
         # concreta de MAF expone el método (algunas lo ocultan si es
         # experimental). Si existe, lo intentamos.
         if hasattr(agent, "run_stream"):
            try:
               # run_stream() devuelve un AsyncIterable[AgentRunResponseUpdate].
               # Cada update tiene .text con el fragmento INCREMENTAL (no
               # acumulado) de lo que el modelo lleva generado.
               async for chunk in agent.run_stream(query):
                  # Algunos updates pueden venir vacíos (metadatos, function
                  # calls internos, etc.) — solo emitimos los que traen texto.
                  if chunk.text:
                     yield chunk.text
               return   # streaming real OK, salimos del generator
            except (TypeError, AttributeError):
               # Firma incompatible con la versión instalada, o el método
               # existe pero no se comporta como async generator. Caemos
               # al fallback. NO capturamos excepciones genéricas (red,
               # auth, etc.) porque esas deben propagarse a la UI.
               pass

         # --- Estrategia 2 (fallback): run() + fake streaming -------------
         # En esta versión de MAF `agent.run(query)` SÍ funciona (es lo que
         # usa el script de consola y ya lo tienes validado). Obtenemos la
         # respuesta completa de una sola vez y la emitimos palabra a
         # palabra con un pequeño delay. El usuario ve aparecer el texto
         # progresivamente, igual que con streaming real.
         result = await agent.run(query)
         text = result.text or ""
         if not text:
            return   # respuesta vacía: nada que simular

         # Dividimos en palabras. `split(' ')` las separa PERO pierde los
         # espacios, así que los re-añadimos al emitir (excepto en la
         # última palabra para no dejar un espacio colgando al final).
         words = text.split(" ")
         for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
            # 25 ms entre palabras ~= 40 palabras/segundo, velocidad de
            # lectura cómoda. Súbelo (0.01) si lo notas muy lento, bájalo
            # (0.05) si lo notas muy rápido. NO uses 0: se vería instantáneo
            # y perdería el efecto.
            await asyncio.sleep(0.025)

   # --- Puente async -> sync --------------------------------------------------
   # asyncio.run() monta un loop, ejecuta la corutina y cierra el loop. Eso
   # NO nos sirve para streaming: queremos mantener el loop vivo mientras
   # llegan chunks. La solución estándar es crear un loop dedicado y extraer
   # los chunks uno a uno con `run_until_complete(agen.__anext__())`.
   loop = asyncio.new_event_loop()
   asyncio.set_event_loop(loop)
   agen = _stream()

   try:
      while True:
         try:
            # Bloquea hasta que llega el siguiente chunk (o hasta StopAsyncIteration).
            chunk = loop.run_until_complete(agen.__anext__())
            yield chunk            # entregamos el chunk al caller (Streamlit)
         except StopAsyncIteration:
            # El async generator terminó: salimos del while limpiamente.
            break
   finally:
      # Pase lo que pase (éxito, excepción, KeyboardInterrupt) cerramos el loop
      # para no dejar hilos colgados.
      loop.close()


# -----------------------------
# Resolver el agente al arrancar
# -----------------------------
# Llamamos a la función 1. Recibe el nombre + versión y devuelve un
# AgentVersionDetails con .name y .version poblados. Si falla, paramos la app
# con un error claro (igual que en el script de consola).
try:
   # Pasamos None si AGENT_VERSION no está fijada en el .env, para que
   # resolve_agent haga auto-detect de la última versión publicada en Foundry.
   # El cache_resource invalida automáticamente la entrada cuando cambia
   # el valor de la env var, así que editar el .env y recargar ya toma
   # la nueva versión sin tener que reiniciar Streamlit.
   resolved = resolve_agent(PROJECT_ENDPOINT, AGENT_NAME, AGENT_VERSION or None)
except Exception as e:
   st.error("Failed to resolve the Foundry agent (check `az login` and project endpoint).")
   st.exception(e)
   st.stop()


# -----------------------------
# Sidebar: info del agente + acciones
# -----------------------------
with st.sidebar:
   st.header("Agent info")
   st.caption(f"Project endpoint: `{PROJECT_ENDPOINT}`")
   st.caption(f"Agent: **{resolved.name}**")
   st.caption(f"Version: **{resolved.version}**")
   st.divider()
   # Botón para borrar el historial sin tener que recargar la página.
   # `st.rerun()` fuerza un rerun inmediato para que la UI refleje el cambio.
   if st.button("🗑️ Clear conversation", use_container_width=True):
      st.session_state.messages = []
      st.rerun()


# -----------------------------
# Inicializar historial de chat en session_state
# -----------------------------
# session_state persiste entre reruns de Streamlit, así que el historial de
# mensajes sobrevive a cada "send". Cada mensaje es un dict con:
#   - "role":    "user" | "assistant"
#   - "content": el texto (markdown renderizable)
if "messages" not in st.session_state:
   st.session_state.messages = []


# -----------------------------
# Pintar el historial existente (todos los turnos previos)
# -----------------------------
# Recorremos el historial y pintamos cada mensaje con su rol对应的 avatar.
# ChatGPT-style: el usuario a la derecha, el asistente a la izquierda.
for message in st.session_state.messages:
   with st.chat_message(message["role"]):
      # markdown en vez de text: así el agente puede devolver listas,
      # tablas, código, etc. con formato.
      st.markdown(message["content"])


# -----------------------------
# Input del usuario (chat_input)
# -----------------------------
# st.chat_input() es el input "pegajoso" en la parte de abajo, igual que
# ChatGPT. Devuelve None si el usuario no ha enviado nada en este rerun.
if prompt := st.chat_input("Type your message to the support agent..."):
   # --- Paso 1: pintar y guardar el mensaje del usuario -----------------
   st.session_state.messages.append({"role": "user", "content": prompt})
   with st.chat_message("user"):
      st.markdown(prompt)

   # --- Paso 2: generar la respuesta del asistente EN STREAMING ----------
   with st.chat_message("assistant"):
      # st.empty() es un contenedor que podemos sobre-escribir las veces
      # que queramos. Lo usamos como "buffer" del streaming: en cada chunk
      # actualizamos su contenido con el texto acumulado hasta el momento.
      placeholder = st.empty()
      full_response = ""

      try:
         # El generador síncrono va produciendo chunks uno a uno (gracias
         # al puente async->sync de run_agent_stream). Por cada chunk:
         for chunk in run_agent_stream(
            project_endpoint=PROJECT_ENDPOINT,
            agent_name=resolved.name,         # nombre del agente recuperado
            agent_version=resolved.version,   # versión concreta
            query=prompt,
         ):
            full_response += chunk
            # Pintamos el texto acumulado + un cursor "▌" para que se vea
            # que el modelo está escribiendo. En cada nuevo chunk se
            # reescribe el contenedor entero (es lo que da el efecto
            # de "ir apareciendo" carácter a carácter).
            placeholder.markdown(full_response + "▌")

         # Cuando el stream termina, reescribimos SIN cursor para que
         # quede la respuesta limpia final.
         placeholder.markdown(full_response)

      except Exception as e:
         st.error("Agent call failed.")
         st.exception(e)
         full_response = "_Error: the agent did not produce a response._"
         placeholder.markdown(full_response)

   # --- Paso 3: guardar la respuesta del asistente en el historial ------
   # Se guarda DESPUÉS del bloque `with` para que `full_response` ya
   # contenga la versión final (sin el cursor "▌").
   st.session_state.messages.append({"role": "assistant", "content": full_response})
