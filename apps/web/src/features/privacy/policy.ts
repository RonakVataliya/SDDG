/**
 * NFR5a / NFR5d. The wording is owned by task N3 (Privacy Policy text) and is a PLACEHOLDER until N3 lands.
 * Bump POLICY_VERSION on any change. Bump AI_SECTION_VERSION only when the AI-processing section changes:
 * that is what re-asks every user for consent.
 */
export const POLICY_VERSION = '2026-09-01'
export const POLICY_DATE = '2026-09-01'
export const AI_SECTION_VERSION = '2026-09-01'

export type PolicySection = { id: string; heading: string; body: string[] }

export const aiSection: PolicySection = {
  id: 'ai-processing',
  heading: 'How your requirements are processed',
  body: [
    'To extract actors, entities and other modelling information, the text you submit is sent to Groq, an external AI service. Nothing is sent until you agree on the consent screen.',
    'To draw a diagram, a text description of the diagram (not your original document) is sent to Kroki, an external rendering service.',
    'We record the date and time you agreed and the version of this section you agreed to. If this section changes, we ask you again before sending anything further.',
  ],
}

export const sections: PolicySection[] = [
  {
    id: 'data',
    heading: 'What we store',
    body: [
      'Your email address, the projects you create, the requirement text you submit, the items extracted from it, and the diagrams generated from them.',
    ],
  },
  aiSection,
  {
    id: 'retention',
    heading: 'Retention and deletion',
    body: ['Retention periods and how to delete your data will be described here (see the Data Retention and Deletion Policy).'],
  },
  {
    id: 'contact',
    heading: 'Contact',
    body: ['Questions about this policy go to the SDDG team (IT314 Group 27).'],
  },
]
