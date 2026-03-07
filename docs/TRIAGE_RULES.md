# Demo Triage Rules

Condition

Child pneumonia risk

Rule

If

age_under_5 = true
fever = true
fast_breathing = true

Then

Urgent Referral

Condition

Child fever but breathing normal

Then

PHC Visit

Condition

Adult mild fever

Then

Home Care