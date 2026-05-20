# API And Configuration Analysis

Use this reference when extracting callable surfaces, parameters, return shapes, source locations, and configuration behavior.

## API Candidate Kinds

- `http-route`: Express/Fastify/Koa/Nest, FastAPI/Flask/Django, Axum/Actix, Gin/Chi, Spring, ASP.NET.
- `sdk-export`: public export from package entrypoints, `pub fn`/`pub struct`, Python package `__init__`, TypeScript barrel export.
- `cli-command`: clap/argparse/click/commander/yargs/cobra subcommands and arguments.
- `rpc-service`: `.proto`, tRPC, JSON-RPC, service traits/interfaces.
- `websocket-message`: socket handlers, message enum variants, channel subscriptions.
- `worker-function`: project-specific task/function/trigger registration surfaces.
- `internal-service`: service-layer method that defines an important module contract.

## Required API Fields

For each candidate, capture:

- name, route, command, or exported symbol
- method/path/channel when applicable
- parameters with type/default/required when available
- request or message shape
- return/response shape
- behavior from doc/comment/source name, with confidence
- source file and 1-based line number
- owner module and evidence pattern

## Search Patterns

Prefer `rg -n` over slower search tools.

### TypeScript / JavaScript

```bash
rg -n "app\\.(get|post|put|delete|patch)|router\\.(get|post|put|delete|patch)|fastify\\.(get|post|put|delete|patch)|@Controller|@Get\\(|@Post\\(|export (async )?function|export class|export const|program\\.command|\\.command\\(" .
```

Look for `package.json` `exports`, `main`, `module`, `types`, and package entrypoints.

### Python

```bash
rg -n "@(app|router)\\.(get|post|put|delete|patch)|@app\\.route|urlpatterns|def |async def |class |argparse|click\\.command|typer\\." .
```

Extract FastAPI/Pydantic parameter and response models when visible.

### Rust

```bash
rg -n "\\.route\\(|Router::new|#\\[(get|post|put|delete|patch)\\(|pub (async )?fn|pub struct|pub enum|clap|Subcommand|Args" .
```

For `clap`, capture subcommands, `Args` structs, and field-level `#[arg(...)]` metadata.

### Go

```bash
rg -n "\\.(GET|POST|PUT|DELETE|PATCH)\\(|HandleFunc\\(|func .*\\(|cobra\\.Command" .
```

### gRPC / GraphQL / WebSocket

```bash
rg -n "service .*\\{|rpc .*\\(|type Query|type Mutation|websocket|WebSocket|socket\\.|subscribe|publish|channel" .
```

For GraphQL, capture root types and resolver fields separately. For WebSocket or pub/sub code, capture the channel/event name as `path`, the handler operation as `method`, and mark payload shape as `tentative` unless a DTO/message type is directly visible.

### Spring / ASP.NET / Actix

```bash
rg -n "@(GetMapping|PostMapping|RequestMapping)|\\[Http(Get|Post|Put|Delete|Patch)|Map(Get|Post|Put|Delete|Patch)\\(|web::resource|#\\[(get|post|put|delete|patch)" .
```

Treat framework route annotations as confirmed source locations. Treat request and return shapes as tentative until handler signatures or DTO types are captured.

## Configuration Extraction

Capture config sources and precedence when visible:

- environment variables: `process.env`, `os.getenv`, `std::env`, `env!`, `os.Getenv`, `System.getenv`
- config files: YAML, JSON, TOML, INI, `.env`, `config.*`, `application.*`
- validation schema: Pydantic settings, Zod/Joi, serde config structs, Viper, Spring `@ConfigurationProperties`
- feature flags and runtime toggles
- secrets management: secret references are useful; hardcoded secret-like values are risks

When precedence is visible, record it explicitly: defaults, config file, environment override, CLI argument, runtime database setting, and feature-flag override. If precedence is not visible, record only the source locations and leave behavior tentative.

Do not copy secrets into durable wiki pages. Record only the variable name, file, line, and risk classification.

## Build And Deploy Extraction

Capture:

- package scripts, Makefile targets, cargo/npm/pnpm/yarn/uv/go/maven/gradle commands
- Dockerfiles, compose files, Kubernetes, Helm, Terraform, cloud config
- CI workflow triggers, jobs, publish/release steps
- runtime requirements such as ports, services, DBs, queues, caches, object stores

## Security And Debt Signals

Capture source-located signals for:

- authentication and authorization middleware, RBAC checks, token validation, OAuth/OIDC setup
- data protection, encryption, PII handling, logging of sensitive values
- technical debt markers such as TODO/FIXME, deprecated APIs, large files, broad modules, global state
- performance and scalability hints: N+1 database access, unbounded queues, blocking IO in async paths, single-writer bottlenecks
