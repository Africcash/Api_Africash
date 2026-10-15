# AfriCash Backend & Soroban Escrow Contract (MVP)

AfriCash brings the familiar cash-agent / POS model to Stellar Testnet. It enables users holding USDC on Stellar to discover local cash agents, initiate cash-out requests, lock USDC in a non-custodial Soroban escrow contract, receive physical cash from the agent, and release the locked USDC once the handover is confirmed.

---

## Architecture Overview

AfriCash operates on a non-custodial model: **AfriCash never takes custody of user funds or private keys**.

```
+-----------------------------------------------------------------------------------+
|                                  React Frontend                                   |
|                          (Stellar Wallets Kit Integration)                        |
+----------------------------------------+------------------------------------------+
                    |                    |                      |
                    | 1. Wallet Auth     | 2. Discover Agents   | 4. Sign Soroban Lock Tx
                    |    Challenge/Verify|    Initiate Cash-Out |    Sign Release Tx
                    v                    v                      v
+---------------------------------------------------+  +----------------------------+
|                AfriCash Backend API               |  |  Stellar Testnet / Soroban |
|  - Django REST Framework (Python 3.9+)            |  |                            |
|  - Non-custodial Ed25519 Wallet Authentication   |  |  +----------------------+   |
|  - Rate Limiting & Input Sanitization             |  |  | AfriCash Escrow      |   |
|  - Agent Discovery & Cache (Redis)                |  |  | Smart Contract       |   |
|  - Postgres DB (Docker Compose)                   |  |  | (Rust / Protocol 28) |   |
|  - MinIO S3 Object Storage (Docker Compose)       |  |  +----------------------+   |
|  - Swagger UI & ReDoc API Documentation           |  |                            |
+---------------------------------------------------+  +----------------------------+
```

### Core Lifecycle

1. **Discovery**: User browses cash agents by location, supported currency (e.g. NGN, GHS, KES), fee, availability, and rating.
2. **Initiation**: User initiates cash-out for a given USDC amount. Backend server generates an exchange reference, computes the fiat payout from agent rates, and creates a secure 6-digit OTP secret and SHA-256 secret hash.
3. **Escrow Lock**: User signs a transaction in their connected Stellar wallet calling `lock_funds` on the Soroban escrow contract. USDC is locked in the contract.
4. **Funding Notification**: Frontend notifies API (`POST /api/exchanges/{id}/notify-funded/`) with the Stellar transaction hash. Status becomes `FUNDED`.
5. **Physical Cash Handover**: User meets agent at the agent's POS stall. Agent provides physical cash.
6. **Confirmation & Release**:
   - **Method A (Direct)**: User confirms receipt directly from wallet (`release_by_user` on-chain or `POST /api/exchanges/{id}/confirm-cash/`).
   - **Method B (OTP)**: User shows the 6-digit OTP secret to the agent. Agent verifies OTP (`release_with_secret` on-chain or via API).
7. **Completion**: USDC is transferred directly from the escrow contract to the agent.
8. **Refund / Cancellation**: If the agent is unavailable, the agent can cancel instantly (`cancel_by_agent`). If timeout expires without completion, the user can claim a full refund (`refund`).

---

## Repository Structure

```
AfriCash/
├── Contracts/                             # Soroban smart contract workspace
│   ├── Cargo.toml
│   └── contracts/
│       └── africash_escrow/
│           ├── Cargo.toml
│           ├── src/
│           │   ├── lib.rs                 # Escrow contract implementation
│           │   └── test.rs                # 7 unit tests (lock, release, refund, cancel)
│           └── Makefile
├── Core/                                  # Django project settings & routing
│   ├── settings.py                        # DB, Redis cache, Throttling, drf-spectacular
│   ├── urls.py                            # Routes, Swagger UI, ReDoc, OpenAPI schema
│   ├── wsgi.py
│   └── asgi.py
├── api/                                   # REST API application
│   ├── authentication.py                  # Stellar wallet challenge/verify & DRF auth
│   ├── security.py                        # Ed25519 signature verify, StrKey validation, sanitization
│   ├── models.py                          # AgentProfile, Exchange models
│   ├── serializers.py                     # Strict serializers with input validation
│   ├── auth_views.py                      # /api/auth/challenge/, /api/auth/verify/, /api/auth/me/
│   ├── views.py                           # AgentViewSet, ExchangeViewSet, ConfigView
│   ├── urls.py                            # API routes
│   ├── admin.py                           # Django admin interface
│   └── tests/                             # Automated test suite (20 tests)
│       ├── test_auth.py
│       ├── test_agents.py
│       ├── test_exchanges.py
│       ├── test_security.py
│       ├── test_docs.py
│       └── test_throttling.py
├── docs/                                  # Detailed integration guides
│   ├── FRONTEND_INTEGRATION.md            # React + Stellar Wallets Kit guide
│   └── CONTRACT_SPEC.md                   # Soroban escrow contract interface
├── docker-compose.yml                     # Multi-container setup (Backend, Postgres, Redis, MinIO)
├── Dockerfile                             # Production-ready backend Dockerfile
├── requirements.txt                       # Python dependencies (includes boto3, django-storages)
├── .env.example                           # Example environment configuration
└── manage.py
```

---

## Quick Start with Docker Compose

The easiest way to run the entire backend stack (API, PostgreSQL 16, Redis 7, MinIO S3) is using Docker Compose:

### 1. Clone & Configure Environment

```bash
cp .env.example .env
```

### 2. Start Services

```bash
docker compose up --build
```

This starts:
- **AfriCash Backend**: `http://localhost:8000`
- **Django Admin**: `http://localhost:8000/admin/` (auto-provisioned: user `admin`, password `admin1234`)
- **PostgreSQL Database**: `localhost:5432` (`africash_db`)
- **Redis Cache**: `localhost:6379`
- **MinIO Object Storage API**: `http://localhost:9000` (bucket `africash-media` auto-provisioned)
- **MinIO Web Console**: `http://localhost:9001` (user: `minioadmin`, pass: `minioadmin`)

### 3. Verify Health & Documentation

Once started, open your browser:
- **Django Admin Dashboard**: [http://localhost:8000/admin/](http://localhost:8000/admin/)
- **Swagger UI Interactive Docs**: [http://localhost:8000/api/docs/](http://localhost:8000/api/docs/)
- **ReDoc Documentation**: [http://localhost:8000/api/redoc/](http://localhost:8000/api/redoc/)
- **OpenAPI 3.0 Schema**: [http://localhost:8000/api/schema/](http://localhost:8000/api/schema/)
- **Network Configuration**: [http://localhost:8000/api/config/](http://localhost:8000/api/config/)

---

## Local Development Setup (Without Docker)

### Prerequisites

- Python 3.9+
- Rust 1.84+ & Cargo
- Stellar CLI (`stellar 28+`)
- Rust target: `wasm32v1-none` (`rustup target add wasm32v1-none`)

### 1. Backend Setup

```bash
# 1. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create .env file
cp .env.example .env

# 4. Run database migrations (uses SQLite by default when DB_HOST is empty)
python manage.py migrate

# 5. Run automated tests
python manage.py test api.tests

# 6. Start development server
python manage.py runserver 0.0.0.0:8000
```

### 2. Frontend Setup (React + Vite + TailwindCSS)

```bash
cd frontend

# 1. Install dependencies
npm install

# 2. Run Vite development server
npm run dev
```

The frontend will run at [http://localhost:5173](http://localhost:5173) with Stellar Wallets Kit support.

---

## Soroban Smart Contract

The escrow contract is located in `Contracts/contracts/africash_escrow`.

### Contract Functions

| Function | Signer | Description |
|---|---|---|
| `__constructor(admin)` | Admin | Deploys contract and sets admin address |
| `lock_funds(exchange_id, user, agent, token, amount, secret_hash, timeout_timestamp)` | User | Locks USDC in contract and sets timeout & secret hash |
| `release_by_user(exchange_id)` | User | User confirms cash handover and releases USDC to agent |
| `release_with_secret(exchange_id, secret)` | Agent | Agent provides 6-digit OTP secret provided by user to claim USDC |
| `refund(exchange_id)` | User | User claims refund of locked USDC after `timeout_timestamp` |
| `cancel_by_agent(exchange_id)` | Agent | Agent cancels trade before completion, returning USDC immediately to user |
| `get_exchange(exchange_id)` | None | Queries current exchange status and escrow details |

### Testing the Smart Contract

```bash
cd Contracts
cargo test
```

All 7 test cases execute against the Soroban test host, verifying token transfers, authorization checks, secret validation, timeouts, and cancellations.

### Building Contract to WASM

```bash
cd Contracts
stellar contract build
```

This compiles optimized WASM to `Contracts/target/wasm32v1-none/release/africash_escrow.wasm`.

### Deploying to Stellar Testnet

```bash
# 1. Generate and fund a deployment identity
stellar keys generate deployer --network testnet --fund

# 2. Deploy WASM with constructor admin parameter
stellar contract deploy \
  --wasm target/wasm32v1-none/release/africash_escrow.wasm \
  --source-account deployer \
  --network testnet \
  -- \
  --admin $(stellar keys address deployer)
```

### Live Testnet Contract

- **Contract ID**: `CCX2P2KDVKVVMX55OPUVYESN5XD73GEJ7EWLNZWNMNLAVZIQVZH5RNRC`
- **Deployment Transaction**: [`d7a84ff8d3444b57f14d233f07512caa15c27257fb5a62ac86737219cfc7f733`](https://stellar.expert/explorer/testnet/tx/d7a84ff8d3444b57f14d233f07512caa15c27257fb5a62ac86737219cfc7f733)
- **Stellar Expert Explorer**: [https://stellar.expert/explorer/testnet/contract/CCX2P2KDVKVVMX55OPUVYESN5XD73GEJ7EWLNZWNMNLAVZIQVZH5RNRC](https://stellar.expert/explorer/testnet/contract/CCX2P2KDVKVVMX55OPUVYESN5XD73GEJ7EWLNZWNMNLAVZIQVZH5RNRC)
- **Stellar Lab**: [https://lab.stellar.org/r/testnet/contract/CCX2P2KDVKVVMX55OPUVYESN5XD73GEJ7EWLNZWNMNLAVZIQVZH5RNRC](https://lab.stellar.org/r/testnet/contract/CCX2P2KDVKVVMX55OPUVYESN5XD73GEJ7EWLNZWNMNLAVZIQVZH5RNRC)

---

## Wallet Authentication (Stellar Wallets Kit)

Users authenticate non-custodially using their connected Stellar wallet (via [Stellar Wallets Kit](https://stellarwalletskit.dev/kit-structure.html)).

### Authentication Flow

1. **Step 1: Request Challenge**
   - Frontend calls `POST /api/auth/challenge/` with `{ "stellar_address": "G..." }`.
   - Backend responds with `{ "message": "...", "nonce": "...", "expires_in": 900 }` (configurable via `CHALLENGE_TIMEOUT_SECONDS`, default 15 minutes).
2. **Step 2: Wallet Signature**
   - Frontend prompts user's wallet to sign the message string.
3. **Step 3: Verify Signature**
   - Frontend calls `POST /api/auth/verify/` with `{ "stellar_address": "G...", "nonce": "...", "signature": "<base64_sig>" }`.
   - Backend cryptographically verifies the Ed25519 signature using `stellar-sdk` and issues a session token.
4. **Step 4: Authenticated Requests**
   - Include the header: `Authorization: Bearer <token>` (or `Authorization: Token <token>`).
   - For local development connecting the Next.js frontend (`africcash` on `http://localhost:3000`) to the backend on `http://localhost:8000`, configure `NEXT_PUBLIC_API_URL=http://localhost:8000/api` in `africcash/.env.local`.

For detailed React code samples and configuration, see [docs/FRONTEND_INTEGRATION.md](docs/FRONTEND_INTEGRATION.md).

---

## API Endpoints Reference

### Authentication & User Profiles
- `POST /api/auth/challenge/`: Request cryptographic challenge nonce
- `POST /api/auth/verify/`: Verify wallet signature and get session token + user profile (`display_name`, `avatar_url`)
- `GET /api/auth/me/`: Get authenticated wallet profile (display name, avatar URL, agent status)
- `PATCH /api/auth/me/`: Update user profile picture (`avatar_url`) and display name

### Object Storage (MinIO)
- `POST /api/upload/`: Upload profile picture or agent storefront image to MinIO S3 object storage (max 5MB, JPG/PNG/WEBP/GIF). Returns `{ "url": "...", "object_key": "...", ... }`.

### Cash Agents
- `GET /api/agents/`: List and discover cash agents (cached, filter by `search`, `currency`, `city`, `available`, `verified`)
- `GET /api/agents/{id}/`: Get specific agent details (includes operating hours, handover methods, and verification badge)
- `POST /api/agents/`: Register as a cash agent (requires wallet auth)
- `GET /api/agents/me/`: Get own agent profile
- `PATCH /api/agents/me/`: Update availability, rates, or profile (invalidates cache)
- `GET /api/agents/me/stats/`: Agent dashboard statistics (completed trades, total volume, active trades, estimated earnings)
- `GET /api/agents/{id}/reviews/`: Get previous customer reviews and star ratings for an agent

### Exchanges & Escrow
- `POST /api/exchanges/`: Initiate a cash-out exchange (computes fiat payout, generates OTP secret & hash)
- `GET /api/exchanges/`: List exchanges for authenticated wallet (filter by `status=ACTIVE|COMPLETED|CANCELLED` or `role=user|agent`)
- `GET /api/exchanges/{id}/`: Get exchange details (includes OTP secret, agent & user avatars, on-chain transaction hashes)
- `POST /api/exchanges/{id}/notify-funded/`: Record on-chain lock transaction hash (`INITIATED -> FUNDED`)
- `POST /api/exchanges/{id}/confirm-cash/`: Confirm cash handover (`FUNDED -> CASH_CONFIRMED`)
- `POST /api/exchanges/{id}/notify-released/`: Record release transaction hash (`-> RELEASED`)
- `POST /api/exchanges/{id}/cancel/`: Cancel trade or record refund transaction hash
- `POST /api/exchanges/{id}/dispute/`: Flag trade dispute if handover issues arise
- `POST /api/exchanges/{id}/review/`: Post 1-5 star review & feedback post-exchange (auto-updates agent rating)

### System Configuration
- `GET /api/config/`: Retrieve network passphrase, RPC URL, Horizon URL, USDC contract ID, and Escrow contract ID

---

## Security Features

1. **Non-Custodial Architecture**: Neither private keys nor user funds are handled by the server. Escrow logic executes directly on Soroban smart contracts.
2. **Replay-Attack Protection**: Wallet challenge nonces expire after 5 minutes and are single-use (immediately invalidated upon verification).
3. **Rate Limiting**: Configured with DRF Throttling:
   - Anonymous requests: `100/minute`
   - Authenticated users: `1000/minute`
   - Authentication challenge/verify: `30/minute`
   - Exchange actions: `60/minute`
4. **Input Sanitization & Validation**:
   - Strict Stellar public key format validation (StrKey Ed25519 verification).
   - HTML and script injection stripping via `sanitize_text`.
   - Numeric validation on all exchange amounts and currency rates.
5. **Caching Layer**: Agent listings and rates are cached in Redis (with LocMem fallback), automatically invalidated upon agent updates.
6. **CORS Security**: Cross-Origin Resource Sharing configured for React/Vite/Next.js frontend origins.

---

## Running Verification Commands

```bash
# 1. Run Smart Contract Unit Tests
cd Contracts && cargo test

# 2. Build Smart Contract WASM
cd Contracts && stellar contract build

# 3. Run Backend API Tests
python manage.py test api.tests

# 4. Validate OpenAPI Schema
python manage.py spectacular --validate
```
