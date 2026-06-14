# Foundry Bridge Specification

## Purpose
Defines how the backend talks to the deployed Foundry agent (`customer-support-agent` v1, `gpt-5-mini`): resolving the agent, creating and reusing server-side conversations, streaming deltas to the WS layer, and coupling stream lifecycle to message persistence.

## Requirements

### Requirement: Foundry agent resolution
The system MUST resolve the agent once per process by name + version, reusing the same `AIProjectClient` and `FoundryAgent` across all requests. Failures MUST surface as `1011` on WS and `503` on REST.

#### Scenario: Cold start
- GIVEN `FOUNDRY_PROJECT_ENDPOINT`, `AZURE_AI_AGENT_NAME`, `AGENT_VERSION` are set
- WHEN the first WS connects
- THEN the backend opens `AIProjectClient` over `AzureCliCredential` and constructs a single `FoundryAgent` reused for the process lifetime.

### Requirement: Conversation reuse via service-side session
The system MUST treat `conversations.foundry_conversation_id` as the server-side conversation handle. On a new conversation, the system MUST mint a fresh session on the first user turn and persist the service id. On subsequent turns, the system MUST resume via `agent.get_session(service_session_id=...)`.

#### Scenario: First turn
- GIVEN `foundry_conversation_id = NULL`
- WHEN the first user turn runs
- THEN the backend calls `agent.create_session()` and passes it to `agent.run(text, stream=True, session=session)`, then persists the returned `service_session_id` on the row.

#### Scenario: Subsequent turn
- GIVEN `foundry_conversation_id = "f-sid"`
- WHEN a new user turn runs
- THEN the backend builds a session via `agent.get_session(service_session_id="f-sid")` and the agent sees the prior turns server-side.

#### Scenario: Lost service session
- GIVEN the stored id is no longer valid
- WHEN `get_session` or the run fails with "conversation not found"
- THEN the backend clears `foundry_conversation_id` to NULL and creates a fresh session (replaying from persisted `messages` is best-effort; release 1 may start clean and log a warning).

### Requirement: Streaming primitive
The system MUST call `agent.run(text, stream=True, session=session)` and iterate the returned `ResponseStream` with `async for update in stream`. Each non-empty `update.text` MUST be forwarded as one `assistant_delta`. After the loop, the system MUST obtain the aggregated text via `await stream.get_final_response()` (or by accumulating deltas) and persist it once.

#### Scenario: Forward deltas
- GIVEN N deltas from the agent
- WHEN the backend iterates
- THEN for each non-empty `update.text` the backend emits exactly one `assistant_delta`; empty updates are skipped.

#### Scenario: Finalize
- GIVEN the loop completes
- WHEN finalization runs
- THEN the backend calls `await stream.get_final_response()` and uses `response.text` (or the accumulated deltas) as the assistant content.

#### Scenario: Client disconnect mid-stream
- GIVEN the WS closes mid-stream
- WHEN the backend detects it
- THEN it cancels the Foundry task and the partial assistant message is NOT persisted.

### Requirement: Persistence coupling
The system MUST persist exactly once per turn: the user message BEFORE the run starts; the assistant final text ONCE on stream completion. Per-token persistence is forbidden.

#### Scenario: User persisted first
- GIVEN an inbound turn
- WHEN the handler starts
- THEN the `user` row is committed before `agent.run(...)` is called.

#### Scenario: Assistant persisted once
- GIVEN a successful run
- WHEN finalized
- THEN exactly one `assistant` row is inserted; no per-delta rows.

#### Scenario: Failure leaves no orphan assistant
- GIVEN the user row was persisted and the run fails
- WHEN the error is handled
- THEN no `assistant` row is inserted and an `error` frame is sent.

### Requirement: Foundry error mapping
Exceptions MUST map to: `foundry_transient` (5xx, 429, timeout), `foundry_auth` (credentials), `foundry_payload` (400-class), `agent_not_found` (resolution). The original exception MUST be logged at WARN with the correlation id.

### Requirement: Foundry client lifecycle
The `AIProjectClient` and `AzureCliCredential` MUST live in an `async with` at app startup and MUST be closed on shutdown. Per-request client creation is forbidden.

### Requirement: Foundry model and prompt are source of truth
The system MUST NOT redefine the system prompt, model name, or agent instructions on the client. Only the user's `content` and the conversation id are sent per turn.
