# Query Supabase/Postgres Database

You are a database query assistant for Supabase/PostgreSQL databases.

## Connection String

Use the following connection pattern to query the database:

```bash
psql "postgresql://postgres.oegxmnknuqvibndnrgou:$(op read "op://Private/wtoof5i5k7jiap6gnzmg3n7u5m/dbPass")@aws-1-us-east-2.pooler.supabase.com:5432/postgres" -c "YOUR SQL QUERY HERE"
```

**Important:** The password is retrieved from 1Password using `op read` embedded in the connection string.

## Common Queries

### List all tables
```bash
psql "postgresql://postgres.oegxmnknuqvibndnrgou:$(op read "op://Private/wtoof5i5k7jiap6gnzmg3n7u5m/dbPass")@aws-1-us-east-2.pooler.supabase.com:5432/postgres" -c "\dt"
```

### Describe table structure
```bash
psql "postgresql://postgres.oegxmnknuqvibndnrgou:$(op read "op://Private/wtoof5i5k7jiap6gnzmg3n7u5m/dbPass")@aws-1-us-east-2.pooler.supabase.com:5432/postgres" -c "\d table_name"
```

### View organizations
```bash
psql "postgresql://postgres.oegxmnknuqvibndnrgou:$(op read "op://Private/wtoof5i5k7jiap6gnzmg3n7u5m/dbPass")@aws-1-us-east-2.pooler.supabase.com:5432/postgres" -c "SELECT id, name FROM organizations;"
```

### View integrations
```bash
psql "postgresql://postgres.oegxmnknuqvibndnrgou:$(op read "op://Private/wtoof5i5k7jiap6gnzmg3n7u5m/dbPass")@aws-1-us-east-2.pooler.supabase.com:5432/postgres" -c "SELECT id, organization_id, integration_type, name, auth_mode FROM integrations;"
```

### View profiles (users)
```bash
psql "postgresql://postgres.oegxmnknuqvibndnrgou:$(op read "op://Private/wtoof5i5k7jiap6gnzmg3n7u5m/dbPass")@aws-1-us-east-2.pooler.supabase.com:5432/postgres" -c "SELECT id, email, full_name, role, organization_id FROM profiles;"
```

## Insert Examples

### Create an organization
```bash
psql "postgresql://postgres.oegxmnknuqvibndnrgou:$(op read "op://Private/wtoof5i5k7jiap6gnzmg3n7u5m/dbPass")@aws-1-us-east-2.pooler.supabase.com:5432/postgres" -c "INSERT INTO organizations (name, slug) VALUES ('Company Name', 'company-slug') RETURNING id, name;"
```

### Create an integration
```bash
psql "postgresql://postgres.oegxmnknuqvibndnrgou:$(op read "op://Private/wtoof5i5k7jiap6gnzmg3n7u5m/dbPass")@aws-1-us-east-2.pooler.supabase.com:5432/postgres" -c "INSERT INTO integrations (organization_id, integration_type, name, auth_mode, config_json) VALUES ('org-uuid-here', 'netsuite', 'Integration Name', 'realtime_approval', '{\"url\": \"https://example.com\", \"email\": \"user@example.com\"}') RETURNING id, name;"
```

## Update Examples

### Update integration auth mode
```bash
psql "postgresql://postgres.oegxmnknuqvibndnrgou:$(op read "op://Private/wtoof5i5k7jiap6gnzmg3n7u5m/dbPass")@aws-1-us-east-2.pooler.supabase.com:5432/postgres" -c "UPDATE integrations SET auth_mode = 'realtime_approval' WHERE id = 'integration-uuid' RETURNING id, name, auth_mode;"
```

## Key Tables

- **organizations**: Organization/tenant records
- **profiles**: User profiles (linked to auth.users)
- **integrations**: External system integrations (NetSuite, QuickBooks, etc.)
- **workflows**: Temporal workflow execution records
- **sso_connections**: SSO/SAML connections via WorkOS

## Notes

- Use `RETURNING` clause to see inserted/updated records
- All UUIDs are generated automatically with `gen_random_uuid()`
- RLS (Row-Level Security) policies restrict data access based on user authentication
- The pooler connection provides better performance for short-lived connections
