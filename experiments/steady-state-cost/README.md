# Cost reconciliation experiment

This experiment consumes the steady-state cost contract defined in `usekarma/aws-config` and produces read-only AWS cost evidence.

It intentionally does **not** call `scripts/deploy.sh` and has no apply, destroy, delete, or mutation path.

## Run

Check out the matching `aws-config` branch or merged contract, then run:

```bash
python scripts/reconcile_steady_state_costs.py \
  --contract ../aws-config/governance/steady_state_costs.json \
  --profile strall.com=<strall-production-profile> \
  --profile usekarma.dev=prod-karma \
  --output evidence/cost-reconciliation.json
```

By default the tool reconciles the previous complete calendar month using Cost Explorer `UnblendedCost`, grouped by AWS service. Each target must have an explicit AWS CLI profile mapping.

Exit codes:

- `0`: each target matches its declared monthly target to the cent
- `1`: invalid contract, missing profile mapping, or AWS CLI/read failure
- `2`: reconciliation completed but the observed cost differs from the target

## Safety boundary

This first slice proves only cost reconciliation at the account level. It records the authenticated account ID and caller ARN, service-level spend, exact variance, and a PASS/FAIL result.

It does **not yet** prove desired-resource vs actual-resource inventory. That is the next slice of the experiment and should remain read-only before any remediation plan is considered.
