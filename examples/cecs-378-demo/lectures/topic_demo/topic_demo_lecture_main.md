---
title: Demo Topic — Security Fundamentals
course: CECS 378
topic-slug: topic_demo
term: su26
adversarial-thinking: false
type: lecture-main
visibility: public
tags: [cecs-378, teaching, security, lecture-main]
icon: LiGraduationCap
iconColor: var(--text-normal)
---

# Demo Topic — Security Fundamentals

## Learning Objectives

- Define the CIA triad and explain why each property matters for secure systems. #objective
- Describe the difference between a vulnerability and an exploit. #objective

## Vocabulary

- **confidentiality** — the property that information is not disclosed to unauthorized parties #vocab #section/vocab [slide:: 2] [citation:: Textbook Ch. 1]
- **integrity** — the property that data has not been altered in an unauthorized way #vocab #section/vocab [slide:: 2] [citation:: Textbook Ch. 1]

## I. The CIA Triad (15 min)

### Concepts

- Confidentiality, Integrity, and Availability are the three foundational properties of secure systems. #concept #section/I [slide:: 3] [citation:: Textbook Ch. 1]
- A vulnerability is a weakness in a system; an exploit is code or technique that leverages it. #concept #section/I [slide:: 4] [citation:: Textbook Ch. 1]

### Cornell blanks

- Confidentiality, Integrity, and _______ form the CIA triad, the foundational properties of secure systems. #blank #section/I [slide:: 3] [answer:: Availability] [citation:: Textbook Ch. 1]
- A _______ is a weakness in a system; an exploit actively leverages that weakness. #blank #section/I [slide:: 4] [answer:: vulnerability] [citation:: Textbook Ch. 1]

## II. Threats and Vulnerabilities (15 min)

### Concepts

- A threat is a potential cause of an unwanted incident; it differs from an attack, which is an active attempt. #concept #section/II [slide:: 5] [citation:: Textbook Ch. 1]

### Cornell blanks

- A threat is a potential cause of an unwanted incident, whereas an _______ is an active attempt to exploit a vulnerability. #blank #section/II [slide:: 5] [answer:: attack] [citation:: Textbook Ch. 1]

## Question Bank

### MC

- #question #type/mc #difficulty/1 #section/I #exam-eligible [answer:: C] [points:: 2] [slide:: 3]
  Stem: Which of the following is NOT a component of the CIA triad?
  - A. Confidentiality
  - B. Integrity
  - C. Authentication
  - D. Availability

## Self-Quiz

- #self-quiz #section/I `Q1.` List the three components of the CIA triad and give one example of a control that supports each.
- #self-quiz #section/II `Q2.` Distinguish a threat from a vulnerability in one sentence each.

## Summary

The CIA triad — Confidentiality, Integrity, Availability — provides the foundational framework for evaluating the security posture of any system. Threats and vulnerabilities are related but distinct; understanding the difference is prerequisite to selecting appropriate controls.

## References

- Textbook Ch. 1 — Introduction to Security

## Slide deck source

- #slide [slide:: 1] [layout:: title] **Demo Topic — Security Fundamentals** [tagline:: The building blocks of secure systems.]
- #slide [slide:: 2] [layout:: vocab] **Key Terms**
  - Confidentiality, Integrity, Availability
- #slide [slide:: 3] [layout:: concept] **The CIA Triad**
  - Confidentiality: limit disclosure
  - Integrity: prevent unauthorized modification
  - Availability: ensure access when needed
- #slide [slide:: 4] [layout:: concept] **Vulnerability vs Exploit**
  - Vulnerability: the weakness
  - Exploit: the weaponized technique
- #slide [slide:: 5] [layout:: concept] **Threats vs Attacks**
  - Threat: potential cause of unwanted incident
  - Attack: active attempt to exploit a vulnerability
