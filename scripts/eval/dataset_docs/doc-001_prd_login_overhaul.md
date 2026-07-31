# PRD: Login & Authentication Overhaul

**Status:** Approved  
**Date:** 2026-07-15  
**Author:** Product Team

## Overview

This document describes the planned overhaul of the login and authentication
system for the customer portal. The changes span new features, modifications to
existing flows, and data schema updates.

## Two-Factor Authentication

Add SMS-based two-factor authentication to the login flow. After entering
username and password, users will receive a 6-digit code via SMS. The code
must be entered within 5 minutes. This is a new feature.

**Affected systems:** auth-service, sms-gateway, user-db

**Schema changes:**
- `users.phone_number`: NEW field, VARCHAR(15), required for 2FA
- `users.two_factor_enabled`: NEW field, BOOLEAN, default false

## Password Reset Flow

Modify the existing password reset flow to support magic links in addition to
the current email-based reset. Users will have the option to receive a one-click
magic link that logs them in and prompts for a new password.

**Affected systems:** auth-service, email-service

**Schema changes:**
- `password_reset_tokens.token_type`: MODIFIED — was VARCHAR(8), now VARCHAR(16) to support "magic_link" values

## Session Timeout

The session timeout behaviour remains unchanged. Sessions expire after 30
minutes of inactivity. No changes to this system.

**Affected systems:** none

## Old Basic Auth Endpoint

The legacy `/api/v1/basic-auth` endpoint is being removed. All clients have
migrated to OAuth 2.0 as of Q1 2026.

**Affected systems:** api-gateway, legacy-proxy

**Schema changes:**
- `api_keys.basic_auth_support`: REMOVED — column dropped
