## Role-Based Auth Backend

This project implements a **role-based authentication & authorization** backend with a dedicated **Super Admin** who can create and manage three roles:

- `MANAGER`
- `LOGISTIQUE`
- `APPROVISIONNEUR`

Only the **SUPER_ADMIN** can create, activate/deactivate, and reset passwords for user accounts.

### Tech Stack (chosen & rationale)

- **Backend**: Node.js + Express + TypeScript  
  Simple, explicit control over middleware and routing; easy to audit security rules.
- **Database**: PostgreSQL  
  Robust, widely supported, great with Prisma.
- **ORM**: Prisma  
  Type-safe queries, clear schema, and straightforward migrations.
- **Auth**: JWT (access + refresh) with **bcrypt** password hashing.

---

## Setup

### 1. Install dependencies

From the `rbac-auth` folder:

```bash
npm install
```

### 2. Configure environment variables

Create a `.env` file in `rbac-auth`:

```bash
DATABASE_URL="postgresql://USER:PASSWORD@localhost:5432/rbac_auth?schema=public"
JWT_ACCESS_SECRET="replace-with-strong-random-string"
JWT_REFRESH_SECRET="replace-with-strong-random-string"
JWT_ACCESS_TTL="15m"
JWT_REFRESH_TTL="7d"
PORT=4000
```

### 3. Database schema & migrations

```bash
npx prisma migrate dev --name init
npx prisma generate
```

This creates the `User` and `RefreshToken` tables:

- `User { id, email, password, role, isActive, createdAt, updatedAt }`
- `RefreshToken { id, userId, token, expiresAt, createdAt }`

### 4. Create the first Super Admin

Use the Prisma CLI or any SQL client to insert a first `SUPER_ADMIN` user. Example with Prisma:

```bash
npx prisma db seed
```

Or run a one-off Node script (example logic):

```ts
import { prisma } from "./src/prisma";
import bcrypt from "bcrypt";
import { Role } from "@prisma/client";

async function main() {
  const hashed = await bcrypt.hash("SuperAdmin123!", 10);
  await prisma.user.create({
    data: {
      email: "superadmin@example.com",
      password: hashed,
      role: Role.SUPER_ADMIN,
      isActive: true,
    },
  });
}

main().catch(console.error);
```

After that, log in with:

- **email**: `superadmin@example.com`
- **password**: `SuperAdmin123!` (change immediately in production).

### 5. Run the server

```bash
npm run dev
```

Server listens on `http://localhost:4000`.

---

## API

### Auth

- `POST /auth/login`

  ```json
  {
    "email": "user@example.com",
    "password": "secret123"
  }
  ```

  Response:

  ```json
  {
    "accessToken": "...",
    "refreshToken": "..."
  }
  ```

- `POST /auth/refresh`

  ```json
  {
    "refreshToken": "..."
  }
  ```

Returns new access + refresh tokens.

### Super Admin–only (all require `Authorization: Bearer <accessToken>` with role `SUPER_ADMIN`)

- `POST /admin/users` – **create user**

  ```json
  {
    "email": "manager1@example.com",
    "password": "StrongPass123",
    "role": "MANAGER" // or LOGISTIQUE, APPROVISIONNEUR
  }
  ```

- `GET /admin/users` – **list all users**
- `PATCH /admin/users/:id/activate` – set `isActive = true`
- `PATCH /admin/users/:id/deactivate` – set `isActive = false`
- `PATCH /admin/users/:id/reset-password`

  ```json
  {
    "password": "NewStrongPass123"
  }
  ```

Inactive users cannot log in and refresh tokens for inactive users are rejected.

---

## Testing

Run unit tests:

```bash
npm test
```

Included tests:

- Basic `AuthService` behavior for invalid credentials.
- `requireSuperAdmin` middleware to ensure only `SUPER_ADMIN` passes the guard.

---

## Extensibility Notes

- Frontend can consume this API using React + TypeScript:
  - Login page uses `/auth/login`.
  - Super Admin dashboard uses `/admin/users` routes for:
    - user list,
    - create form,
    - activate/deactivate buttons,
    - reset password action.
- Additional role-specific dashboards (manager/logistique/approvisionneur) are implemented on the frontend, which simply check `role` in the decoded JWT and route-guard accordingly.


