# Multi-Tier Web App on AWS

A simple task/notes manager (Flask + MySQL) deployed on a production-style,
highly-available AWS architecture — built as a hands-on portfolio project to
demonstrate core AWS networking, compute, and database fundamentals.

## Architecture

```
                            Internet
                               |
                        Internet Gateway
                               |
              ┌────────────────────────────────┐
              │        Public Subnets           │
              │      (public-a, public-b)       │
              │                                  │
              │   Application Load Balancer      │
              │        NAT Instance (fck-nat)    │
              └────────────────┬─────────────────┘
                                |
              ┌────────────────────────────────┐
              │        Private Subnets          │
              │     (private-a, private-b)      │
              │                                  │
              │   EC2 Auto Scaling Group         │
              │   (Flask app, port 5000)         │
              └────────────────┬─────────────────┘
                                |
              ┌────────────────────────────────┐
              │       Isolated Subnets          │
              │    (isolated-a, isolated-b)     │
              │                                  │
              │      RDS MySQL (db.t4g.micro)   │
              └──────────────────────────────────┘
```

- **VPC**: `10.0.0.0/16`, spanning 2 Availability Zones for high availability
- **Public subnets**: host the Application Load Balancer and a NAT instance
- **Private subnets**: host the EC2 Auto Scaling Group running the Flask app
  (no direct internet access — outbound traffic routes through the NAT instance)
- **Isolated subnets**: host RDS MySQL, with no route to the internet at all

## Security group chain

Traffic is only allowed to flow one hop at a time, each restricted to the
previous layer's security group rather than open IP ranges:

| Security Group | Inbound Rule |
|---|---|
| `alb-sg` | HTTP (80) from `0.0.0.0/0` |
| `ec2-sg` | Custom TCP (5000) from `alb-sg` only |
| `rds-sg` | MySQL (3306) from `ec2-sg` only |
| `nat-sg` | All traffic from VPC CIDR (`10.0.0.0/16`) |

This means RDS is unreachable from the internet, and EC2 is unreachable
except through the load balancer — a standard defense-in-depth pattern.

## Components

- **VPC & Subnets**: 6 subnets (2 public, 2 private, 2 isolated) across 2 AZs
- **Internet Gateway**: provides internet access to public subnets
- **NAT Instance**: a free-tier-eligible EC2 instance (`fck-nat` AMI) that lets
  private-subnet EC2 instances reach the internet (e.g. for OS/package
  updates) without being reachable from it
- **RDS (MySQL)**: `db.t4g.micro`, deployed in isolated subnets, no public
  access, password authentication
- **Launch Template**: defines the EC2 configuration (AMI, security group,
  and a user-data script that installs Python, deploys the Flask app, and
  registers it as a systemd service so it restarts automatically on failure)
- **Auto Scaling Group**: spans both private subnets, desired capacity 2,
  min 1 / max 4, with a target-tracking scaling policy (60% average CPU)
- **Application Load Balancer**: internet-facing, listens on port 80,
  forwards to a target group on port 5000, with health checks against `/health`

## Application

A minimal Flask CRUD app (task/notes manager):
- `GET /` — serves the web UI
- `GET /health` — health check endpoint used by the ALB target group
- `GET/POST/PUT/DELETE /api/tasks[/<id>]` — full CRUD API backed by MySQL

Kept intentionally simple so the AWS architecture stays the focus of the
project, not application complexity.

## Debugging notes (real issues hit during setup)

Documenting these because working through them was as valuable as the build
itself:

1. **NAT instance had no real public IP** — the auto-assigned IP was in the
   `100.64.0.0/10` CGNAT range, not a routable AWS public IP. Fixed by
   allocating and attaching an Elastic IP instead.
2. **SSH `-J` (ProxyJump) flag didn't pass the identity file to the jump
   host** on this OpenSSH client version — worked around by defining both
   hosts explicitly in `~/.ssh/config` with per-host `IdentityFile` entries.
3. **Windows `.pem` file permissions too open** — SSH refused to use the key
   until Windows ACLs were restricted to a single user via `icacls`.
4. **RDS password with special characters got corrupted** when pasted into
   the launch template's user-data field, causing `Access denied` errors and
   ASG targets stuck "unhealthy." Diagnosed via SSH (through the NAT
   instance) and `journalctl` logs, and resolved by switching to a simple
   alphanumeric password to avoid shell-escaping issues entirely.

## Cost notes

Approximate running cost if left on continuously (all within AWS's ~6-month,
$100-credit "Free Tier" for new accounts as of 2026):

| Resource | Approx. cost |
|---|---|
| RDS `db.t4g.micro` | ~$14/month |
| NAT instance `t4g.nano` | ~$4-6/month |
| 2x ASG EC2 instances | ~$12/month |
| Application Load Balancer | ~$16/month + data |

## Possible next steps

- Load test with a tool like `hey` to observe the Auto Scaling Group scale
  out and back in based on CPU
- Add HTTPS via an ACM certificate and an HTTPS listener on the ALB
- Move infrastructure to Terraform or CloudFormation for repeatability
- Add CloudWatch alarms/dashboards for observability
