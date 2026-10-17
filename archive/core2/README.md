# Historical Core2 experiment

The Core2 is bricked and retired from the active project. Source, contracts and
regression tests are retained for historical analysis only. This directory is
outside active Terraform/configuration discovery; do not deploy it. Git history
and existing private evidence remain intact. Relative module references in archived
Terraform describe its original location, not a new runnable deployment component.

Archiving source is not teardown or state migration. Existing resources, if any,
retain their original state ownership until independently reconciled. Read-only
inspection found no current iot-digital-twin state keys in the intended backend,
but IoT/Lambda/DynamoDB inspection was denied; absence is NOT established.
