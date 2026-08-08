# H-Zero — VPC Module
# Two distinct network zones:
#   1. private-internal: LLM inference + database (no internet)
#   2. isolated-egress: browser fleet outbound traffic
# Plus public subnets for API/Nginx ingress

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "h-zero-${var.environment}-vpc"
    Project     = "h-zero"
    Environment = var.environment
  }
}

# ── Private Internal Subnets (LLM + DB, no internet) ────────────────────────

resource "aws_subnet" "private_internal" {
  count             = length(var.private_subnet_cidrs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index % length(var.availability_zones)]

  # No auto-assign public IP — these are truly private
  map_public_ip_on_launch = false

  tags = {
    Name        = "h-zero-${var.environment}-private-internal-${count.index + 1}"
    Zone        = "private-internal"
    SubnetRole  = "llm-database"
  }
}

# ── Isolated Egress Subnets (browser fleet outbound only) ───────────────────

resource "aws_subnet" "isolated_egress" {
  count             = length(var.egress_subnet_cidrs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.egress_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index % length(var.availability_zones)]

  map_public_ip_on_launch = false

  tags = {
    Name        = "h-zero-${var.environment}-isolated-egress-${count.index + 1}"
    Zone        = "isolated-egress"
    SubnetRole  = "browser-fleet"
  }
}

# ── Public Subnets (API + Nginx ingress) ────────────────────────────────────

resource "aws_subnet" "public" {
  count             = length(var.public_subnet_cidrs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.public_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index % length(var.availability_zones)]

  map_public_ip_on_launch = true

  tags = {
    Name        = "h-zero-${var.environment}-public-${count.index + 1}"
    Zone        = "public"
    SubnetRole  = "api-ingress"
  }
}

# ── Internet Gateway (public subnets only) ──────────────────────────────────

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "h-zero-${var.environment}-igw"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "h-zero-${var.environment}-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# ── NAT Gateway (for isolated egress subnets — browser fleet outbound) ──────

resource "aws_eip" "nat" {
  domain = "vpc"
}

resource "aws_nat_gateway" "egress" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id

  tags = {
    Name = "h-zero-${var.environment}-nat-egress"
  }
}

resource "aws_route_table" "egress" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.egress.id
  }

  tags = {
    Name = "h-zero-${var.environment}-egress-rt"
  }
}

resource "aws_route_table_association" "egress" {
  count          = length(aws_subnet.isolated_egress)
  subnet_id      = aws_subnet.isolated_egress[count.index].id
  route_table_id = aws_route_table.egress.id
}

# ── VPC Endpoint for S3 (shared, reduces NAT costs) ─────────────────────────

resource "aws_vpc_endpoint" "s3" {
  vpc_id       = aws_vpc.main.id
  service_name = "com.amazonaws.${var.aws_region}.s3"

  tags = {
    Name = "h-zero-${var.environment}-s3-endpoint"
  }
}

# ── Network ACLs ────────────────────────────────────────────────────────────

resource "aws_network_acl" "private_internal" {
  vpc_id     = aws_vpc.main.id
  subnet_ids = aws_subnet.private_internal[*].id

  # Block all inbound from internet
  ingress {
    protocol   = -1
    rule_no    = 100
    action     = "allow"
    cidr_block = var.vpc_cidr
    from_port  = 0
    to_port    = 0
  }

  # Block all outbound to internet
  egress {
    protocol   = -1
    rule_no    = 100
    action     = "allow"
    cidr_block = var.vpc_cidr
    from_port  = 0
    to_port    = 0
  }

  tags = {
    Name = "h-zero-${var.environment}-private-nacl"
  }
}

resource "aws_network_acl" "egress" {
  vpc_id     = aws_vpc.main.id
  subnet_ids = aws_subnet.isolated_egress[*].id

  # No inbound — egress subnets are outgoing-only
  egress {
    protocol   = -1
    rule_no    = 100
    action     = "allow"
    cidr_block = "0.0.0.0/0"
    from_port  = 0
    to_port    = 0
  }

  tags = {
    Name = "h-zero-${var.environment}-egress-nacl"
  }
}

# ── Outputs ─────────────────────────────────────────────────────────────────

output "vpc_id" {
  value = aws_vpc.main.id
}

output "private_subnet_ids" {
  value = aws_subnet.private_internal[*].id
}

output "egress_subnet_ids" {
  value = aws_subnet.isolated_egress[*].id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "database_endpoint" {
  value = "h-zero-db.${var.environment}.internal"
}
