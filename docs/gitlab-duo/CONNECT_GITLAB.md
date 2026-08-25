# Connect Shadow to GitLab Ultimate Trial

## Owner-only action
GitLab needs account authorization to access the canonical GitHub repository. This cannot be completed by repository code alone.

Recommended architecture: keep GitHub canonical and use GitLab as an external CI / independent agent verification plane.

## One-time UI path
1. GitLab.com -> Create new -> New project/repository.
2. Choose **Run CI/CD for external repository**.
3. Choose **GitHub**.
4. Authorize/connect GitHub when prompted.
5. Select repository **lemurcina/lemurijanac**.
6. Keep GitHub as source of truth / pull mirror. Do not switch to bidirectional mirroring.
7. Create/connect the project.

The repo already contains `.gitlab-ci.yml`, so the first GitLab pipeline should start after the external repository connection is established.

## After connection
Enable GitLab Duo Agent Platform for the project/group if the trial UI asks. Then create/enable three custom workstreams from `docs/gitlab-duo/SHADOW_AGENT_CONTRACT.md`:
- Shadow Red Team
- CI Recovery
- Integration Verifier

Do not grant automatic approval for financial, outbound, credential, destructive, or binding actions. Keep human approval on sensitive tool actions.

## Acceptance evidence
Connection is considered DONE only when:
- GitLab project visibly tracks `lemurcina/lemurijanac`;
- a pipeline reads `.gitlab-ci.yml`;
- ruff + pytest + adversarial/failure gates execute;
- the project exposes AI > Sessions / Agent Platform;
- no source-of-truth conflict or bidirectional mirror is enabled.
