#![no_std]
use soroban_sdk::{
    contract, contracterror, contractevent, contractimpl, contracttype,
    token::TokenClient, Address, Bytes, BytesN, Env,
};

// Storage TTL bounds in ledgers (~5 seconds per ledger)
const BUMP_THRESHOLD: u32 = 30 * 17280;
const BUMP_TO: u32 = 120 * 17280;

#[contracttype]
#[derive(Copy, Clone, Debug, Eq, PartialEq)]
#[repr(u32)]
pub enum ExchangeStatus {
    Funded = 1,
    Released = 2,
    Refunded = 3,
    Cancelled = 4,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Exchange {
    pub exchange_id: u64,
    pub user: Address,
    pub agent: Address,
    pub token: Address,
    pub amount: i128,
    pub secret_hash: BytesN<32>,
    pub timeout_timestamp: u64,
    pub status: ExchangeStatus,
    pub created_at: u64,
}

#[contracttype]
#[derive(Clone)]
pub enum DataKey {
    Admin,
    Exchange(u64),
}

#[contracterror]
#[derive(Copy, Clone, Debug, Eq, PartialEq)]
#[repr(u32)]
pub enum EscrowError {
    NotInitialized = 1,
    ExchangeAlreadyExists = 2,
    ExchangeNotFound = 3,
    InvalidAmount = 4,
    InvalidStatus = 5,
    InvalidSecret = 6,
    TimeoutNotReached = 7,
    InvalidTimeout = 8,
}

#[contractevent]
pub struct ExchangeFunded {
    #[topic]
    pub exchange_id: u64,
    #[topic]
    pub user: Address,
    #[topic]
    pub agent: Address,
    pub amount: i128,
}

#[contractevent]
pub struct ExchangeReleased {
    #[topic]
    pub exchange_id: u64,
    #[topic]
    pub agent: Address,
    pub amount: i128,
}

#[contractevent]
pub struct ExchangeRefunded {
    #[topic]
    pub exchange_id: u64,
    #[topic]
    pub user: Address,
    pub amount: i128,
}

#[contractevent]
pub struct ExchangeCancelled {
    #[topic]
    pub exchange_id: u64,
    #[topic]
    pub agent: Address,
    pub amount: i128,
}

#[contract]
pub struct AfricCashEscrow;

#[contractimpl]
impl AfricCashEscrow {
    // Constructor initializes admin address
    pub fn __constructor(env: Env, admin: Address) {
        env.storage().instance().set(&DataKey::Admin, &admin);
    }

    // Lock USDC in escrow for an exchange
    pub fn lock_funds(
        env: Env,
        exchange_id: u64,
        user: Address,
        agent: Address,
        token: Address,
        amount: i128,
        secret_hash: BytesN<32>,
        timeout_timestamp: u64,
    ) -> Result<(), EscrowError> {
        if amount <= 0 {
            return Err(EscrowError::InvalidAmount);
        }

        let now = env.ledger().timestamp();
        if timeout_timestamp <= now {
            return Err(EscrowError::InvalidTimeout);
        }

        let key = DataKey::Exchange(exchange_id);
        if env.storage().persistent().has(&key) {
            return Err(EscrowError::ExchangeAlreadyExists);
        }

        // Require authorization from the user providing funds
        user.require_auth();

        // Transfer tokens from user into escrow contract
        let contract_address = env.current_contract_address();
        let token_client = TokenClient::new(&env, &token);
        token_client.transfer(&user, &contract_address, &amount);

        let exchange = Exchange {
            exchange_id,
            user: user.clone(),
            agent: agent.clone(),
            token,
            amount,
            secret_hash,
            timeout_timestamp,
            status: ExchangeStatus::Funded,
            created_at: now,
        };

        env.storage().persistent().set(&key, &exchange);
        env.storage().persistent().extend_ttl(&key, BUMP_THRESHOLD, BUMP_TO);
        env.storage().instance().extend_ttl(BUMP_THRESHOLD, BUMP_TO);

        ExchangeFunded {
            exchange_id,
            user,
            agent,
            amount,
        }
        .publish(&env);

        Ok(())
    }

    // User directly confirms cash receipt and releases locked funds to agent
    pub fn release_by_user(env: Env, exchange_id: u64) -> Result<(), EscrowError> {
        let key = DataKey::Exchange(exchange_id);
        let mut exchange: Exchange = env
            .storage()
            .persistent()
            .get(&key)
            .ok_or(EscrowError::ExchangeNotFound)?;

        if exchange.status != ExchangeStatus::Funded {
            return Err(EscrowError::InvalidStatus);
        }

        // Require authorization from the user
        exchange.user.require_auth();

        exchange.status = ExchangeStatus::Released;
        env.storage().persistent().set(&key, &exchange);

        // Transfer locked tokens to agent
        let contract_address = env.current_contract_address();
        let token_client = TokenClient::new(&env, &exchange.token);
        token_client.transfer(&contract_address, &exchange.agent, &exchange.amount);

        ExchangeReleased {
            exchange_id,
            agent: exchange.agent.clone(),
            amount: exchange.amount,
        }
        .publish(&env);

        Ok(())
    }

    // Agent releases funds by providing secret / OTP shared by user after physical cash handover
    pub fn release_with_secret(env: Env, exchange_id: u64, secret: Bytes) -> Result<(), EscrowError> {
        let key = DataKey::Exchange(exchange_id);
        let mut exchange: Exchange = env
            .storage()
            .persistent()
            .get(&key)
            .ok_or(EscrowError::ExchangeNotFound)?;

        if exchange.status != ExchangeStatus::Funded {
            return Err(EscrowError::InvalidStatus);
        }

        // Require authorization from the agent claiming payment
        exchange.agent.require_auth();

        // Verify SHA-256 hash of provided secret
        let computed_hash: BytesN<32> = env.crypto().sha256(&secret).into();
        if computed_hash != exchange.secret_hash {
            return Err(EscrowError::InvalidSecret);
        }

        exchange.status = ExchangeStatus::Released;
        env.storage().persistent().set(&key, &exchange);

        // Transfer locked tokens to agent
        let contract_address = env.current_contract_address();
        let token_client = TokenClient::new(&env, &exchange.token);
        token_client.transfer(&contract_address, &exchange.agent, &exchange.amount);

        ExchangeReleased {
            exchange_id,
            agent: exchange.agent.clone(),
            amount: exchange.amount,
        }
        .publish(&env);

        Ok(())
    }

    // User claims refund if timeout has elapsed without completion
    pub fn refund(env: Env, exchange_id: u64) -> Result<(), EscrowError> {
        let key = DataKey::Exchange(exchange_id);
        let mut exchange: Exchange = env
            .storage()
            .persistent()
            .get(&key)
            .ok_or(EscrowError::ExchangeNotFound)?;

        if exchange.status != ExchangeStatus::Funded {
            return Err(EscrowError::InvalidStatus);
        }

        // Require user authorization
        exchange.user.require_auth();

        // Enforce timeout
        let now = env.ledger().timestamp();
        if now < exchange.timeout_timestamp {
            return Err(EscrowError::TimeoutNotReached);
        }

        exchange.status = ExchangeStatus::Refunded;
        env.storage().persistent().set(&key, &exchange);

        // Refund tokens back to user
        let contract_address = env.current_contract_address();
        let token_client = TokenClient::new(&env, &exchange.token);
        token_client.transfer(&contract_address, &exchange.user, &exchange.amount);

        ExchangeRefunded {
            exchange_id,
            user: exchange.user.clone(),
            amount: exchange.amount,
        }
        .publish(&env);

        Ok(())
    }

    // Agent can cancel an exchange immediately if unable to provide cash
    pub fn cancel_by_agent(env: Env, exchange_id: u64) -> Result<(), EscrowError> {
        let key = DataKey::Exchange(exchange_id);
        let mut exchange: Exchange = env
            .storage()
            .persistent()
            .get(&key)
            .ok_or(EscrowError::ExchangeNotFound)?;

        if exchange.status != ExchangeStatus::Funded {
            return Err(EscrowError::InvalidStatus);
        }

        // Require agent authorization
        exchange.agent.require_auth();

        exchange.status = ExchangeStatus::Cancelled;
        env.storage().persistent().set(&key, &exchange);

        // Return tokens to user
        let contract_address = env.current_contract_address();
        let token_client = TokenClient::new(&env, &exchange.token);
        token_client.transfer(&contract_address, &exchange.user, &exchange.amount);

        ExchangeCancelled {
            exchange_id,
            agent: exchange.agent.clone(),
            amount: exchange.amount,
        }
        .publish(&env);

        Ok(())
    }

    // Retrieve exchange state
    pub fn get_exchange(env: Env, exchange_id: u64) -> Result<Exchange, EscrowError> {
        let key = DataKey::Exchange(exchange_id);
        env.storage()
            .persistent()
            .get(&key)
            .ok_or(EscrowError::ExchangeNotFound)
    }
}

#[cfg(test)]
mod test;
