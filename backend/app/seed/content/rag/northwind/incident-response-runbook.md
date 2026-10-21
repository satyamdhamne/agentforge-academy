---
title: Incident Response Runbook
allowed_groups: engineering
updated: 2026-02-03
---
# Incident Response Runbook

## Severity levels
SEV1 is a full outage or data loss affecting customers; SEV2 is major degradation of a core feature; SEV3 is minor or partial impact with a workaround; SEV4 has no customer impact.

## Declaring an incident
Anyone can declare an incident in the #incidents channel using the /incident command. For SEV1 and SEV2 the on-call engineer becomes Incident Commander until they hand over explicitly. The Incident Commander assigns a Communications Lead within 15 minutes.

## Response targets
SEV1 incidents must be acknowledged within 5 minutes and a customer status page update must be posted within 30 minutes. SEV2 incidents must be acknowledged within 15 minutes. Status updates are posted every 30 minutes until resolution.

## Rollbacks
If an incident began within one hour of a deploy, the default first action is to roll back that deploy. Rollbacks do not require approval during an active SEV1 or SEV2.

## Postmortems
Every SEV1 and SEV2 requires a blameless postmortem within 5 business days. Postmortems include a timeline, contributing factors, and action items with owners and due dates.
