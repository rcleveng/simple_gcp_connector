# Low Overhead GCP Database Connector.

Low-overhead connections to Google Cloud SQL databases, optionally supporting 
IAM Authentication.

## Prerequisites

-   **Google Cloud Project**: A GCP project with Cloud SQL enabled.
-   **Cloud SQL Instance**: A PostgreSQL instance configured for IAM authentication.

## IAM Authentication (Optional)
-   **IAM User**: A database user mapped to a Google Cloud IAM service account or user.
-   **Authentication**:
    -   Locally: `gcloud auth application-default login`
    -   Production: Service Account attached to the environment (VM, GKE, Cloud Run).

## Poastgres

### 1. Psycopg3 Connection Pool

Example using `psycopg` (version 3) to connect to Cloud SQL. It can automatically resolve the instance IP and inject the IAM token.

**Dependencies:**
- `psycopg` 3.3.0 or higher
- `google-auth`

```python
import psycopg
from psycopg_pool import ConnectionPool
from simple_gcp_connector.psycopg import GoogleCloudConnInfoProvider

# Use the instance connection name (project:region:instance).
INSTANCE_CONNECTION_NAME = "my-project:us-central1:my-instance"
DB_USER = "your-sa-email@your-project.iam" # note there is no .gserviceaccount.com
DB_NAME = "your-database-name" # likely postgres
DATABASE_URL = f"postgresql://{DB_USER}@IGNORED-HOST/{DB_NAME}?sslmode=require"

def create_pool():
    get_conninfo = GoogleCloudConnInfoProvider(
        DATABASE_URL,
        instance_connection_name=INSTANCE_CONNECTION_NAME
    )
    return ConnectionPool(
        conninfo=get_conninfo,
        min_size=1,
        max_size=5
    )

# Usage
with create_pool() as pool:
    with pool.connection() as conn:
        print("Connected!")
        # ... execute queries ...
```

### 2. SQLAlchemy

Use `sqlalchemy` to connect to Cloud SQL. If you are using the instance connection name, it will automatically resolve the instance IP and inject the IAM token unless ```enable_iam_auth``` is set to ```false``` (it's True by default).

**Dependencies:**
- `sqlalchemy`
- `psycopg` (or `pg8000`)
- `google-auth`

```python
import sqlalchemy
from sqlalchemy import create_engine
from simple_gcp_connector.sqlalchemy import register_connector

# Configuration
INSTANCE_CONNECTION_NAME = "my-project:us-central1:my-instance"
DB_USER = "your-sa-email@your-project.iam"
DB_NAME = "your-database-name"

engine = create_engine(
    f"postgresql+psycopg://{DB_USER}@/{DB_NAME}",
    connect_args={"sslmode": "require"}
)

register_connector(engine, instance_connection_name=INSTANCE_CONNECTION_NAME)

# Usage
with engine.connect() as connection:
    result = connection.execute(sqlalchemy.text("SELECT 1"))
    print(result.fetchone())
```

### Note on Cloud SQL Proxy

If you are using the Cloud SQL Auth Proxy (sidecar or local process), you don't need `instance_connection_name`. You can simply point to `127.0.0.1`.

```python
# Psycopg w/ Proxy
get_conninfo = GoogleCloudConnInfoProvider("postgresql://user@127.0.0.1:5432/db")

# SQLAlchemy w/ Proxy
engine = create_engine("postgresql+psycopg://user@127.0.0.1:5432/db")
register_connector(engine)
```

## Setup Notes

- Ensure the Service Account (or user) has the `Cloud SQL Client` role and is added as an IAM user in the Cloud SQL instance.
- If youa `enable_iam_authentication` flag must be set to `on` for your Cloud SQL instance.