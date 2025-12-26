# Multi-Tenant Double-Entry Accounting System

A FastAPI-based multi-tenant double-entry accounting application following SOLID principles and the repository pattern.

## Features

- **Multi-tenancy**: Users can belong to multiple companies and switch between them
- **Double-entry accounting**: Every transaction must balance (debits = credits)
- **Account management**: Full CRUD operations for chart of accounts with hierarchical support
- **Transaction management**: Create, post, and manage journal entries
- **Reporting**: Balance sheets, trial balance, journal reports, and general ledger
- **User management**: Authentication, authorization, and company access control

## Architecture

This application follows Clean/Hexagonal Architecture with four distinct layers:

```
app/
├── domain/          # Enterprise business rules (entities, interfaces)
├── infrastructure/  # Database, external services
├── application/     # Use cases (services)
├── api/             # FastAPI routes, schemas
├── core/            # Configuration, security, exceptions
└── main.py          # Application entry point
```

### Key Design Patterns

- **Repository Pattern**: Abstract data access behind interfaces
- **Dependency Injection**: Services receive their dependencies
- **SOLID Principles**: Single responsibility, Open/closed, Liskov substitution, Interface segregation, Dependency inversion

## Setup

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd homeaccmt26

# Install dependencies with uv
uv sync

# Copy environment configuration
cp .env.example .env
```

### Configuration

Edit `.env` with your settings:

```env
DATABASE_URL=sqlite+aiosqlite:///./data/accounting.db
SECRET_KEY=your-super-secret-key-change-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

### Database Setup

```bash
# Initialize Alembic migrations (first time)
uv run alembic init alembic

# Generate migration
uv run alembic revision --autogenerate -m "Initial migration"

# Run migrations
uv run alembic upgrade head
```

### Running the Application

```bash
# Development
uv run uvicorn app.main:app --reload

# Production
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## API Endpoints

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/login` | Login with email/password and company selection |
| POST | `/api/v1/auth/login/form` | OAuth2-compatible login form |
| GET | `/api/v1/auth/me` | Get current user info |
| GET | `/api/v1/auth/companies` | List user's companies |
| POST | `/api/v1/auth/switch-company/{company_id}` | Switch to another company |

### Users

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/users/` | List users (admin only) |
| POST | `/api/v1/users/` | Create new user |
| GET | `/api/v1/users/{id}` | Get user details |
| PUT | `/api/v1/users/{id}` | Update user |
| DELETE | `/api/v1/users/{id}` | Delete user |
| POST | `/api/v1/users/{id}/companies/{company_id}` | Grant company access |
| DELETE | `/api/v1/users/{id}/companies/{company_id}` | Revoke company access |

### Companies

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/companies/` | List companies |
| POST | `/api/v1/companies/` | Create new company |
| GET | `/api/v1/companies/{id}` | Get company details |
| PUT | `/api/v1/companies/{id}` | Update company |
| DELETE | `/api/v1/companies/{id}` | Delete company |

### Accounts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/accounts/` | List accounts |
| POST | `/api/v1/accounts/` | Create new account |
| GET | `/api/v1/accounts/{id}` | Get account details |
| PUT | `/api/v1/accounts/{id}` | Update account |
| DELETE | `/api/v1/accounts/{id}` | Delete account |
| GET | `/api/v1/accounts/{id}/balance` | Get account balance |

### Transactions

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/transactions/` | List transactions |
| POST | `/api/v1/transactions/` | Create new transaction |
| GET | `/api/v1/transactions/{id}` | Get transaction details |
| PUT | `/api/v1/transactions/{id}` | Update transaction (draft only) |
| DELETE | `/api/v1/transactions/{id}` | Delete transaction (draft only) |
| POST | `/api/v1/transactions/{id}/post` | Post transaction |
| POST | `/api/v1/transactions/{id}/void` | Void posted transaction |

### Reports

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/reports/balance-sheet` | Get balance sheet |
| GET | `/api/v1/reports/trial-balance` | Get trial balance |
| GET | `/api/v1/reports/journal` | Get journal entries |
| GET | `/api/v1/reports/general-ledger/{account_id}` | Get general ledger for account |

## Testing

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/unit/test_entities.py

# Run integration tests
uv run pytest tests/integration/

# Run with coverage
uv run pytest --cov=app
```

## Double-Entry Accounting Rules

1. **Transaction Balance**: Every transaction must have a sum of zero (debits = credits)
2. **Minimum Lines**: Each transaction must have at least two lines
3. **Sign Convention**:
   - Debits are positive amounts
   - Credits are negative amounts
4. **Posted Transactions**: Once posted, transactions cannot be edited (only voided)

### Account Types

- `ASSET`: Resources owned (normally debit balance)
- `LIABILITY`: Obligations owed (normally credit balance)
- `EQUITY`: Owner's stake (normally credit balance)
- `REVENUE`: Income earned (normally credit balance)
- `EXPENSE`: Costs incurred (normally debit balance)

## Project Structure

```
homeaccmt26/
├── app/
│   ├── api/
│   │   ├── schemas/          # Pydantic request/response models
│   │   └── v1/               # API version 1 routes
│   ├── application/
│   │   └── services/         # Business logic services
│   ├── core/
│   │   ├── config.py         # Application settings
│   │   ├── exceptions.py     # Custom exceptions
│   │   └── security.py       # JWT and password handling
│   ├── domain/
│   │   ├── entities/         # Domain entities
│   │   └── repositories/     # Repository interfaces
│   ├── infrastructure/
│   │   ├── database/
│   │   │   ├── models/       # SQLModel ORM models
│   │   │   └── session.py    # Database session management
│   │   └── repositories/     # Repository implementations
│   ├── dependencies.py       # FastAPI dependencies
│   └── main.py               # Application entry point
├── tests/
│   ├── unit/                 # Unit tests
│   └── integration/          # Integration tests
├── .env.example              # Environment template
├── pyproject.toml            # Project configuration
└── README.md                 # This file
```

## License

MIT License
