# Persistence Specification

## Purpose
Defines the database schema (users, conversations, messages), Alembic migrations, async SQLAlchemy engine, and the FastAPI session dependency. Release 1 uses SQLite (aiosqlite) in dev; the engine URL is env-driven so prod can swap to asyncpg without schema changes.

## Requirements

### Requirement: UUID v4 primary keys
Every PK MUST be a `Uuid` column holding a random UUID v4 generated at the application layer. Auto-increment ints, timestamps, and ULIDs MUST NOT be used as PKs. `created_at` is a separate `DateTime` column.

### Requirement: `users` table
Columns: `id` (UUID v4 PK), `entraid_oid` (unique non-null `String`), `email` (nullable), `display_name` (nullable), `last_seen_at` (nullable `DateTime`).

#### Scenario: Uniqueness on `entraid_oid`
- GIVEN an existing `users.entraid_oid = "abc"`
- WHEN a second insert with the same value runs
- THEN the database raises a unique-constraint violation and the upsert service returns the existing row.

#### Scenario: OID separate from PK
- GIVEN a row with `id = "0192...uuid4"` and `entraid_oid = "abc"`
- WHEN read back
- THEN the two columns hold independent values.

### Requirement: `conversations` table
Columns: `id` (UUID v4 PK), `user_id` (UUID v4 FK → `users.id`, indexed), `foundry_conversation_id` (nullable `String`, indexed), `title` (nullable), `created_at` (`DateTime`).

#### Scenario: Create conversation
- GIVEN an authenticated user `u-uuid`
- WHEN the API creates a conversation via `POST /conversations`
- THEN a row is inserted with `id = <new uuid4>`, `user_id = "u-uuid"`, `foundry_conversation_id = NULL`, and the response is the full `ConversationDetailOut` (including `messages: []`).

#### Scenario: Link to Foundry thread
- GIVEN a conversation with `foundry_conversation_id = NULL`
- WHEN the first Foundry call returns a service-side id
- THEN the row is updated and committed before any assistant message is persisted.

#### Scenario: FK enforcement
- GIVEN a non-existent `user_id`
- WHEN an insert runs
- THEN the database raises a FK violation.

### Requirement: `messages` table
Columns: `id` (UUID v4 PK), `conversation_id` (UUID v4 FK, indexed), `role` (`user|assistant|system`), `content` (`Text`), `foundry_message_id` (nullable), `created_at` (`DateTime`).

#### Scenario: Persist user message BEFORE Foundry call
- GIVEN an inbound turn
- WHEN the chat handler starts
- THEN the `user` row is committed before `agent.run(...)` is awaited.

#### Scenario: Persist exactly one assistant message
- GIVEN 87 deltas totalling 412 chars
- WHEN the stream completes
- THEN exactly one `assistant` row with the full text is inserted; no per-delta rows.

#### Scenario: FK cascade
- GIVEN a conversation with N messages
- WHEN the conversation is deleted
- THEN all N messages are removed.

### Requirement: Async engine and session factory
The system MUST expose one async engine and an `async_sessionmaker` configured for `DATABASE_URL`. SQLite MUST enable `PRAGMA foreign_keys = ON` per connection. `echo` MUST be config-driven.

#### Scenario: Session per request
- GIVEN a handler using `get_session`
- WHEN the request runs
- THEN exactly one `AsyncSession` is opened, committed or rolled back, and closed.

### Requirement: Alembic migrations
The initial migration `0001_init` MUST create the three tables with FKs, unique constraints, and indexes. Schema changes MUST land as additional migrations.

#### Scenario: Fresh migrate
- GIVEN an empty database
- WHEN `alembic upgrade head` runs
- THEN `users`, `conversations`, and `messages` exist with the documented schema.

#### Scenario: Idempotent re-run
- GIVEN a DB already at `head`
- WHEN `alembic upgrade head` runs again
- THEN no destructive change occurs.
