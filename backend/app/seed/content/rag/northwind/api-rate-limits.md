---
title: Public API Rate Limits
allowed_groups: everyone
updated: 2026-04-02
---
# Public API Rate Limits

## Default limits
Every API key may send 100 requests per minute and 20,000 requests per day. Limits are enforced per key, not per IP address. Burst traffic above the per-minute limit receives HTTP 429 Too Many Requests with a Retry-After header in seconds.

## Higher limits
Customers on the Business plan get 600 requests per minute. Enterprise customers can request custom limits through their account manager; increases take effect within two business days.

## Best practices
Clients should retry 429 and 503 responses with exponential backoff and jitter, starting at one second and capping at 60 seconds. Never retry 400-level validation errors other than 429. Use the Idempotency-Key header on POST requests so retries cannot create duplicate orders.

## Webhooks
Webhook deliveries are retried up to 8 times over 24 hours. Your endpoint must respond within 10 seconds with a 2xx status, otherwise the delivery counts as failed.
