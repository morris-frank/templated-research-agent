# Contracts Library Example

Reusable contracts package with:
- core domain-agnostic contracts
- agronomy-specific dossier/questionnaire contracts
- markdown renderers
- example agronomy questionnaire spec
- thin workflow stubs showing intended integration boundaries

## Design

Source of truth:
- Pydantic models in `contracts/`

Interchange / configuration:
- YAML questionnaire specs in `examples/`

Human-readable artifacts:
- markdown renderers in `contracts/renderers/`

## Structure

```text
contracts/
  core/
    artifact_meta.py
    evidence.py
    claims.py
    questionnaire.py
  agronomy/
    dossier.py
    questionnaire.py
  renderers/
    markdown.py

examples/
  questionnaire.agronomy.yaml
  build_demo_artifacts.py

workflows/
  agronomy/
    build_dossier.py
    filter_questionnaire.py
    answer_questionnaire.py
Install
pip install pydantic pyyaml
Run demo
python examples/build_demo_artifacts.py

