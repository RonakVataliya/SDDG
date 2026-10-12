/** A small library-system requirement set for trying the flow end to end. */
export const SAMPLE_REQUIREMENTS = `FR1: The librarian shall be able to register a new member with name, email and membership type.
FR2: A member can search the catalogue by title, author or ISBN.
FR3: The librarian shall issue a book to a registered member for 14 days.
FR4: A member can reserve a book that is currently on loan.
FR5: The system shall send a reminder email to the member two days before the due date.
FR6: The librarian shall record the return of a book and calculate any late fee.
FR7: The system shall store every loan in the loan history.
FR8: The administrator can generate a monthly report of overdue loans.

NFR1: Search results should appear within 2 seconds for a catalogue of 50,000 books.`
