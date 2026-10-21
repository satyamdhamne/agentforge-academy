---
title: Information Security Policy
allowed_groups: everyone
updated: 2026-01-10
---
# Information Security Policy

## Access
All employees must use single sign-on with phishing-resistant multi-factor authentication (security keys or passkeys). Access to production requires an approved just-in-time request that expires after 8 hours.

## Secrets
Secrets such as API keys and database passwords must be stored in the company secrets manager. Committing a secret to a repository is a security incident: rotate the secret immediately and report it in the #security channel.

## Devices
Laptops must have full-disk encryption, automatic updates and the endpoint protection agent enabled. Lost or stolen devices must be reported within 24 hours.
