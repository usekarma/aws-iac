# M1-only maintenance sealing extension

This additive extension is independent of maintain_identity_center.py's original
single-ARN contract. No older planner/sealer/apply validation is modified. The
existing PR #22 declaration is reproduced exactly; this PR targets main and can
be reviewed without stacking. It adds no plan generator, AWS operation or apply path.

Scope: existing owner account 835990279085, local backend/default workspace,
lineage adda9261-8df8-2be4-51cf-f829529878b3, state serial 15, one approved saved
plan SHA-256 6b4420f0fd9c9c1c5f44fe4dae0264c1fd21935591d469b3f9a16804856ef34d.
The delta and combined declaration are hash-pinned: exactly seven previously
reviewed read-only additions, no baseline changes, all new grants target account
623155450153, regional grants us-east-1. Cloud Control reads require Resource *;
that bounded broader read exposure remains a human acceptance item.

## Required evidence and trust boundary

Existing operator evidence.json, binary plan, plan.json, maintenance variables,
rollback declaration and log are preserved. To extend that bundle AFTER workflow
review, an operator must supply two new reviewed records; never replace evidence
with invented observations. Missing records stop validation. JSON booleans record
human approval/attestation, not cryptographic authentication; protect the directory
and independently record the manifest hash. Historical boundary/SCP absence is
operator-attested, not proven by this offline sealer.

owner.json must contain only:

- owner_directory: the exact existing review-uhd86fs8 owner path.
- lineage: adda9261-8df8-2be4-51cf-f829529878b3; serial: 15.
- state_sha256: 5b25cc02532bc9c1d42aa89ab7eff4f75d4689f6ea599bc933611fedd7780571.
- verified_evidence_sha256: independently calculated hash of existing evidence.json.

context.json must contain exactly:

```json
{
  "schema_version": 1,
  "operation": "m1-discovery-seal-only",
  "owner_account": "835990279085",
  "grant_account": "623155450153",
  "region": "us-east-1",
  "plan_sha256": "6b4420f0fd9c9c1c5f44fe4dae0264c1fd21935591d469b3f9a16804856ef34d",
  "eventual_reprovisioning_accounts": ["623155450153", "835990279085"],
  "reprovisioning_impact_acknowledged": true,
  "seal_only_approved": true,
  "apply_approved": false
}
```

Those true acknowledgments may be written only when supported by actual human
review. Keep new records private, mode 0600; use exclusive creation, no overwrites.
This change does not create them or seal the real bundle.

## Offline verification / sealing after review

From the reviewed checkout, using the repository verification environment:

```bash
python3 scripts/seal_m1_discovery.py verify --owner-dir /home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8 --review-dir /home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8/maintenance-reviews/m1-discovery-1dhfxzlv
# ONLY after separate workflow review and supported seal-only approval:
python3 scripts/seal_m1_discovery.py seal --owner-dir /home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8 --review-dir /home/ted/dev/aws-iac/artifacts/identity-center-bootstrap/review-uhd86fs8/maintenance-reviews/m1-discovery-1dhfxzlv
```

These calls do not invoke AWS, initialize a backend, generate/refresh a plan,
modify state, install a source overlay or reprovision accounts. terraform show
renders the existing binary only. Binary/JSON, variables, archived managed state,
source and provider lock must agree. Semantic validation requires one known
inline-policy update and six no-ops; drift, replacements, moves/imports and all
assignment/publisher changes fail. Before-attributes must match retained owner
state. Existing evidence inventories must match actual owner file hashes.

Success writes only m1-maintenance-manifest.json, exclusively, mode 0400. It
records owner/review/source hashes and explicitly apply_authorized=false. Existing
manifest cannot be overwritten. Read-only mode is an accidental-edit safeguard,
not an immutable signature; independent manifest-hash custody is required. Avoid
concurrent changes to owner/review/source throughout verification and sealing.

No existing apply implementation accepts this new contract. A future apply path
requires its own review, stale-state/source/binary checks and explicit approval of
both saved-plan AND sealed manifest hashes. Terraform automatically reprovisions
all assigned accounts, including 835990279085, although the new grants are guarded
to 623155450153. No apply permission is inferred from seal approval. Rollback is a
fresh same-owner reverse plan using rollback-declaration.json, separately approved;
never restore old state. ATOM and publisher remain unchanged.

Acceptance: M1-SEAL-01 exact pinned plan/delta/provenance; M1-SEAL-02 owner/context
missing/tampered records fail; M1-SEAL-03 one update/six no-ops; M1-SEAL-04 explicit
two-account acknowledgment; M1-SEAL-05 no overwrite or apply path. Synthetic tests
exercise the seal in temporary fixtures, not the real operator bundle. This is
review preparation, not evidence that production IAM or live boundaries were tested.
