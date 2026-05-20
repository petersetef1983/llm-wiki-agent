# Code Patterns By Language

Use these patterns to guide focused source inspection. They are search hints, not proof by themselves.

## TypeScript / JavaScript

- Entry: `index.ts`, `main.ts`, `server.ts`, `app.ts`, package `exports`.
- API: Express/Fastify/Koa routes, Nest controllers, tRPC routers.
- Config: `process.env`, `config`, `.env`, Zod/Joi schemas.
- Data: Prisma schema, TypeORM entities, Mongoose schemas, SQL files.
- CLI: commander, yargs, oclif, `bin` field.

## Python

- Entry: `__main__.py`, `main.py`, `app.py`, `manage.py`.
- API: FastAPI decorators, Flask routes, Django urls.
- Config: `os.getenv`, Pydantic settings, dynaconf, dotenv.
- Data: SQLAlchemy, Django models, Pydantic schemas, Alembic migrations.
- CLI: argparse, click, typer.

## Rust

- Entry: `src/main.rs`, `src/lib.rs`, `src/bin/*.rs`, `[[bin]]`.
- API: `pub fn`, `pub struct`, `pub enum`, `pub trait`, Axum/Actix routes.
- Config: serde `Deserialize` config structs, `std::env`, `config` crate.
- Data: SQLx, SeaORM, Diesel, serde protocol models.
- CLI: clap `Parser`, `Subcommand`, `Args`.

## Go

- Entry: `cmd/*/main.go`, `main.go`.
- API: Gin/Chi/Echo routes, `http.HandleFunc`.
- Config: envconfig, Viper, `os.Getenv`.
- Data: GORM structs, SQL migrations, protobuf messages.
- CLI: cobra commands and flags.

## Java / C# / Other

- Java: Spring controllers, `@RequestMapping`, JPA entities, Maven/Gradle.
- C#: ASP.NET controllers/minimal APIs, EF models, `.csproj`.
- PHP/Ruby: route files, controllers, ORM models, composer/gem manifests.
- GraphQL: `schema.graphql`, `typeDefs`, resolver maps, `type Query`, `type Mutation`, `type Subscription`.
- WebSocket/eventing: `socket.on`, `ws.on`, `subscribe`, `publish`, channel/message enums.

## Security, Operations, And Debt

- Auth/RBAC: `auth`, `authorize`, `permission`, `role`, `jwt`, `oauth`, `oidc`, middleware/interceptor names.
- Secrets: `secret`, `token`, `password`, `apiKey`; record locations and risk, not secret values.
- Runtime ops: metrics, traces, health checks, readiness/liveness, retry/backoff, queue limits.
- Debt/performance: TODO/FIXME, blocking IO inside async handlers, global state, unbounded collections, singletons.

Always pair pattern matches with source path and line number in the evidence artifact.
