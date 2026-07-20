output "vm_name" {
  value = google_compute_instance.webintel.name
}

output "vm_external_ip" {
  value = google_compute_address.webintel.address
}

output "service_account_email" {
  value = google_service_account.webintel.email
}

output "secret_ids" {
  value = [for s in google_secret_manager_secret.webintel : s.secret_id]
}

output "ssh_via_iap" {
  value = "gcloud compute ssh webintel-mcp --zone=${var.zone} --project=${var.project_id} --tunnel-through-iap"
}
