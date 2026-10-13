# Pilot path

This page sets out what would be needed to run Sikka on real data. It is a proposal for discussion. No entity has agreed to any of the steps below, and nothing here describes an existing arrangement.

## 1. Data sharing agreement checklist

- [ ] Named data owner for each feed (road segment registry, crash records, traffic station counts) and a named recipient.
- [ ] A purpose limited to road safety screening and data quality feedback to producers.
- [ ] The contract fields to be shared, with prohibited personal fields removed at the source.
- [ ] Delivery frequency and the expected delay for late records.
- [ ] Retention periods, deletion on request, and treatment of derived data.
- [ ] Storage location, access control, and encryption in transit and at rest.
- [ ] How the agreement ends.

## 2. Privacy review

- A data protection impact assessment before any real record is processed.
- Data minimisation: no names, identity numbers, phone numbers, plate numbers or free text narratives. Sikka's privacy rules (`SK-P001`, `SK-P002`) quarantine such fields automatically, but the first line of defence is not to send them.
- Role based access and a log of every access to record level data.
- Periodic review of quarantine and access logs.

## 3. Governance roles

| Role | Responsibility |
| --- | --- |
| Contract owner | Approves contract versions and changes under the versioning rule in `contract/CHANGELOG.md` |
| Data steward (per producer) | Answers conformance findings and agrees fixes |
| Producer technical contact | Changes exports so that feeds conform |
| Analyst | Runs rankings, records decisions and abstentions |
| Independent reviewer | Checks method, results and limitations before any use |

## 4. What would change in the contract

- **Shared crash identifiers** between producers, so that duplicate reports can be matched exactly instead of by time and place.
- **An agreed segment registry** with stable identifiers, validity dates and an owner per segment.
- **One severity definition**, with mapping tables for legacy codes agreed with each producer.
- **Continuous station counts** with documented calibration, so that exposure is not estimated from one week.
- **A governance process** for major and minor versions, with the diff tool used for every change.

## 5. Suggested steps

1. Review contract v1 with producers and agree a first version.
2. Run conformance checks on a historical extract with privacy controls in place, and share the reports with producers.
3. Compare rankings with existing engineering judgement before any use.
4. Publish an evaluation with its limitations before any operational decision.
