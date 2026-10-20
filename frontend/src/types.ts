export type AnyRecord = Record<string, any>

export interface Paginated<T = AnyRecord> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface Account extends AnyRecord {
  id: number
  name: string
  type: string
  type_label?: string
  current_balance?: string
}

export interface Category extends AnyRecord {
  id: number
  name: string
  kind: string
  parent?: number | null
  children?: Category[]
}

export interface CreditCard extends AnyRecord {
  id: number
  name: string
  statement_start_day: number
  statement_end_day: number
  due_day: number
  credit_limit: string
}

export interface DebtItem extends AnyRecord {
  id: number
  title: string
  kind: string
  due_date: string
  payable_amount: string
  status: string
}

export interface Loan extends AnyRecord {
  id: number
  name: string
  principal: string
  annual_rate: string
  term_months: number
  stats?: AnyRecord
}
