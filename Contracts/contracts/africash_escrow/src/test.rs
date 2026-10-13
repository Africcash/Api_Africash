#![cfg(test)]
use super::*;
use soroban_sdk::{
    testutils::{Address as _, Ledger},
    token::{StellarAssetClient, TokenClient},
    Address, Bytes, BytesN, Env,
};

fn setup_test(env: &Env) -> (Address, Address, Address, Address, AfricCashEscrowClient<'static>) {
    env.mock_all_auths();

    let admin = Address::generate(env);
    let user = Address::generate(env);
    let agent = Address::generate(env);

    let token_admin = Address::generate(env);
    let token_contract = env.register_stellar_asset_contract_v2(token_admin.clone());
    let token_address = token_contract.address();

    // Mint initial tokens to user
    let token_admin_client = StellarAssetClient::new(env, &token_address);
    token_admin_client.mint(&user, &1000);

    let contract_id = env.register(AfricCashEscrow, (admin.clone(),));
    let escrow_client = AfricCashEscrowClient::new(env, &contract_id);

    (admin, user, agent, token_address, escrow_client)
}

#[test]
fn test_lock_and_release_by_user() {
    let env = Env::default();
    let (_admin, user, agent, token_address, client) = setup_test(&env);
    let token_client = TokenClient::new(&env, &token_address);

    let secret = Bytes::from_slice(&env, b"OTP1234");
    let secret_hash: BytesN<32> = env.crypto().sha256(&secret).into();

    let exchange_id = 101u64;
    let amount = 250i128;
    let timeout = env.ledger().timestamp() + 3600;

    // Lock funds
    client.lock_funds(
        &exchange_id,
        &user,
        &agent,
        &token_address,
        &amount,
        &secret_hash,
        &timeout,
    );

    assert_eq!(token_client.balance(&user), 750);
    assert_eq!(token_client.balance(&client.address), 250);

    let exchange = client.get_exchange(&exchange_id);
    assert_eq!(exchange.status, ExchangeStatus::Funded);
    assert_eq!(exchange.amount, amount);

    // User confirms cash receipt and releases funds
    client.release_by_user(&exchange_id);

    assert_eq!(token_client.balance(&client.address), 0);
    assert_eq!(token_client.balance(&agent), 250);

    let updated_exchange = client.get_exchange(&exchange_id);
    assert_eq!(updated_exchange.status, ExchangeStatus::Released);
}

#[test]
fn test_lock_and_release_with_secret() {
    let env = Env::default();
    let (_admin, user, agent, token_address, client) = setup_test(&env);
    let token_client = TokenClient::new(&env, &token_address);

    let secret = Bytes::from_slice(&env, b"AFRI-7890");
    let secret_hash: BytesN<32> = env.crypto().sha256(&secret).into();

    let exchange_id = 102u64;
    let amount = 300i128;
    let timeout = env.ledger().timestamp() + 3600;

    client.lock_funds(
        &exchange_id,
        &user,
        &agent,
        &token_address,
        &amount,
        &secret_hash,
        &timeout,
    );

    // Release with correct secret
    client.release_with_secret(&exchange_id, &secret);

    assert_eq!(token_client.balance(&agent), 300);
    let exchange = client.get_exchange(&exchange_id);
    assert_eq!(exchange.status, ExchangeStatus::Released);
}

#[test]
fn test_release_with_invalid_secret_fails() {
    let env = Env::default();
    let (_admin, user, agent, token_address, client) = setup_test(&env);

    let secret = Bytes::from_slice(&env, b"SECRET-123");
    let secret_hash: BytesN<32> = env.crypto().sha256(&secret).into();

    let exchange_id = 103u64;
    let amount = 100i128;
    let timeout = env.ledger().timestamp() + 3600;

    client.lock_funds(
        &exchange_id,
        &user,
        &agent,
        &token_address,
        &amount,
        &secret_hash,
        &timeout,
    );

    let wrong_secret = Bytes::from_slice(&env, b"WRONG-SECRET");
    let res = client.try_release_with_secret(&exchange_id, &wrong_secret);
    assert!(res.is_err());
}

#[test]
fn test_refund_after_timeout() {
    let env = Env::default();
    let (_admin, user, agent, token_address, client) = setup_test(&env);
    let token_client = TokenClient::new(&env, &token_address);

    let secret = Bytes::from_slice(&env, b"OTP-REFUND");
    let secret_hash: BytesN<32> = env.crypto().sha256(&secret).into();

    let exchange_id = 104u64;
    let amount = 400i128;
    let timeout = env.ledger().timestamp() + 1800;

    client.lock_funds(
        &exchange_id,
        &user,
        &agent,
        &token_address,
        &amount,
        &secret_hash,
        &timeout,
    );

    // Attempt refund before timeout should fail
    let early_refund = client.try_refund(&exchange_id);
    assert!(early_refund.is_err());

    // Advance ledger timestamp beyond timeout
    env.ledger().set_timestamp(timeout + 10);

    // Refund now succeeds
    client.refund(&exchange_id);

    assert_eq!(token_client.balance(&user), 1000);
    assert_eq!(token_client.balance(&client.address), 0);

    let exchange = client.get_exchange(&exchange_id);
    assert_eq!(exchange.status, ExchangeStatus::Refunded);
}

#[test]
fn test_cancel_by_agent() {
    let env = Env::default();
    let (_admin, user, agent, token_address, client) = setup_test(&env);
    let token_client = TokenClient::new(&env, &token_address);

    let secret = Bytes::from_slice(&env, b"OTP-CANCEL");
    let secret_hash: BytesN<32> = env.crypto().sha256(&secret).into();

    let exchange_id = 105u64;
    let amount = 150i128;
    let timeout = env.ledger().timestamp() + 3600;

    client.lock_funds(
        &exchange_id,
        &user,
        &agent,
        &token_address,
        &amount,
        &secret_hash,
        &timeout,
    );

    // Agent cancels before timeout
    client.cancel_by_agent(&exchange_id);

    assert_eq!(token_client.balance(&user), 1000);
    assert_eq!(token_client.balance(&client.address), 0);

    let exchange = client.get_exchange(&exchange_id);
    assert_eq!(exchange.status, ExchangeStatus::Cancelled);
}

#[test]
fn test_duplicate_exchange_id_fails() {
    let env = Env::default();
    let (_admin, user, agent, token_address, client) = setup_test(&env);

    let secret = Bytes::from_slice(&env, b"OTP-DUP");
    let secret_hash: BytesN<32> = env.crypto().sha256(&secret).into();

    let exchange_id = 106u64;
    let amount = 50i128;
    let timeout = env.ledger().timestamp() + 3600;

    client.lock_funds(
        &exchange_id,
        &user,
        &agent,
        &token_address,
        &amount,
        &secret_hash,
        &timeout,
    );

    // Try creating again with same exchange_id
    let res = client.try_lock_funds(
        &exchange_id,
        &user,
        &agent,
        &token_address,
        &amount,
        &secret_hash,
        &timeout,
    );
    assert!(res.is_err());
}

#[test]
fn test_invalid_amount_and_timeout() {
    let env = Env::default();
    let (_admin, user, agent, token_address, client) = setup_test(&env);

    let secret = Bytes::from_slice(&env, b"OTP-INVALID");
    let secret_hash: BytesN<32> = env.crypto().sha256(&secret).into();

    let exchange_id = 107u64;
    let timeout = env.ledger().timestamp() + 3600;

    // Zero amount fails
    let res_zero = client.try_lock_funds(
        &exchange_id,
        &user,
        &agent,
        &token_address,
        &0,
        &secret_hash,
        &timeout,
    );
    assert!(res_zero.is_err());

    // Set ledger timestamp
    env.ledger().set_timestamp(100);
    let past_timeout = 50u64;
    let res_timeout = client.try_lock_funds(
        &exchange_id,
        &user,
        &agent,
        &token_address,
        &100,
        &secret_hash,
        &past_timeout,
    );
    assert!(res_timeout.is_err());
}
