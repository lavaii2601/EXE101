-- Provider-neutral subscription and payment ledger for the admin finance tab.
-- All statements are idempotent because Railway applies migration files on
-- every deploy.

CREATE TABLE IF NOT EXISTS subscriptions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    provider TEXT NOT NULL DEFAULT 'manual',
    provider_subscription_id TEXT,
    plan_code TEXT NOT NULL,
    plan_name TEXT,
    status TEXT NOT NULL DEFAULT 'incomplete',
    billing_interval TEXT NOT NULL DEFAULT 'monthly',
    currency TEXT NOT NULL DEFAULT 'VND',
    unit_amount BIGINT NOT NULL DEFAULT 0,
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
    canceled_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT subscriptions_status_check CHECK (
        status IN ('trialing', 'active', 'past_due', 'paused', 'canceled', 'incomplete', 'expired')
    ),
    CONSTRAINT subscriptions_interval_check CHECK (
        billing_interval IN ('monthly', 'yearly')
    ),
    CONSTRAINT subscriptions_currency_check CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT subscriptions_amount_check CHECK (unit_amount >= 0)
);

CREATE TABLE IF NOT EXISTS payment_transactions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    subscription_id BIGINT REFERENCES subscriptions(id) ON DELETE SET NULL,
    provider TEXT NOT NULL DEFAULT 'manual',
    provider_payment_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    currency TEXT NOT NULL DEFAULT 'VND',
    gross_amount BIGINT NOT NULL DEFAULT 0,
    fee_amount BIGINT NOT NULL DEFAULT 0,
    refund_amount BIGINT NOT NULL DEFAULT 0,
    description TEXT,
    paid_at TIMESTAMPTZ,
    refunded_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT payment_transactions_status_check CHECK (
        status IN ('pending', 'paid', 'failed', 'partially_refunded', 'refunded')
    ),
    CONSTRAINT payment_transactions_currency_check CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT payment_transactions_amounts_check CHECK (
        gross_amount >= 0 AND fee_amount >= 0 AND refund_amount >= 0
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriptions_provider_external
    ON subscriptions (provider, provider_subscription_id)
    WHERE provider_subscription_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_subscriptions_status_period
    ON subscriptions (status, current_period_end DESC);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_updated
    ON subscriptions (user_id, updated_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_transactions_provider_external
    ON payment_transactions (provider, provider_payment_id)
    WHERE provider_payment_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_payment_transactions_paid_currency
    ON payment_transactions (paid_at DESC, currency)
    WHERE paid_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_payment_transactions_refunded_currency
    ON payment_transactions (refunded_at DESC, currency)
    WHERE refunded_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_payment_transactions_user_created
    ON payment_transactions (user_id, created_at DESC);

DROP TRIGGER IF EXISTS trg_subscriptions_updated_at ON subscriptions;
CREATE TRIGGER trg_subscriptions_updated_at
BEFORE UPDATE ON subscriptions
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_payment_transactions_updated_at ON payment_transactions;
CREATE TRIGGER trg_payment_transactions_updated_at
BEFORE UPDATE ON payment_transactions
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
