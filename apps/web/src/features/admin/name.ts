/** Accounts have no name yet, so a name is made from the email: priya.shah@x -> Priya Shah. */
export const nameOf = (email: string) =>
  email.split('@')[0].split(/[._-]+/).filter(Boolean).map((w) => w[0].toUpperCase() + w.slice(1)).join(' ')
