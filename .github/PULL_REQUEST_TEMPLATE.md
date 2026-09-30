# Pull Request Template

When opening a PR created by an agent, include the following sections.

## Summary
Short description of the change.

## Origin
- Agent: agent:<name>
- Issue: #<number> (if any)

## Agent run log
Include prompts, commands executed, environment variables used, and a short log.

## Tests run
List commands and their outputs (truncate long logs, include links if necessary).

## Security
Confirm that no secrets are included and identify required secret configuration.

## Checklist
- [ ] CI checks passed
- [ ] Reviewed by maintainer
- [ ] Linked to an Issue (if applicable)
