variable "project_id" {
  type        = string
  default     = "homelab-424902"
  description = "GCP project ID."
}

variable "region" {
  type        = string
  default     = "us-central1"
  description = "GCP region for the VM."
}

variable "zone" {
  type        = string
  default     = "us-central1-a"
  description = "GCP zone for the VM."
}

variable "machine_type" {
  type        = string
  default     = "e2-medium"
  description = "Compute machine type. e2-medium (2 vCPU/4GB) fits the Playwright+SearxNG stack."
}

variable "repo_ref" {
  type        = string
  default     = "main"
  description = "Git ref to deploy. Pin to a tag/SHA for production (after the PR merges, switch to main or a release tag)."
}
