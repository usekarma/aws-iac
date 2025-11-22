/*
Note: This is a generated HCL content from the JSON input which is based on the latest API version available.
To import the resource, please run the following command:
terraform import azapi_resource. ?api-version=TODO

Or add the below config:
import {
  id = "?api-version=TODO"
  to = azapi_resource.
}
*/

resource "azapi_resource" "" {
  type      = "@TODO"
  parent_id = "/subscriptions/$${var.subscriptionId}/resourceGroups/$${var.resourceGroupName}"
  name      = ""
  body = {
    ami_id                = "ami-123"
    ami_name              = "mongo-base-20251120T010101"
    exporter_version      = "0.40.0"
    mongo_major           = "7"
    node_exporter_version = "1.8.2"
    root_volume_gb        = 30
    timestamp             = "20251120T010101"
  }
}
