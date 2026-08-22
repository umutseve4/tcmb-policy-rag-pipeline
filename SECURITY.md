# Security Policy

## Supported versions

Only the latest commit on `main` is supported during the pre-1.0 phase.

## Reporting a vulnerability

Do not open a public issue containing exploit details, credentials, or personal data. Report privately through GitHub Security Advisories for this repository. Include reproduction steps, affected version, impact, and a minimal proof of concept.

## Scope

The project fetches user-supplied public URLs. Operators must restrict allowed hosts before exposing ingestion as a service; v0.1 is a local CLI and does not claim server-side request forgery protection for a public deployment.
