import { Agent, run } from '@openserv-labs/sdk'
import { z } from 'zod'

// Our Python backend URL
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:3000'

const agent = new Agent({
  systemPrompt: `You are an accessibility auditor agent. You audit websites for WCAG 2.1 compliance.
Built by a blind developer for blind and low-vision users.
You can audit any URL and return a detailed accessibility report with a score (0-100), grade (A-F),
and breakdown of issues across 12 categories including alt text, heading structure, keyboard navigation,
ARIA attributes, form labels, contrast ratio, and more.
Free audits are available. Paid audits via x402 protocol on Base cost 0.10 USDC.`
})

// Capability 1: Free audit (basic)
agent.addCapability({
  name: 'audit_website_free',
  description: 'Audit a website for WCAG 2.1 accessibility compliance. Returns a score (0-100), grade (A-F), and detailed breakdown of accessibility issues across 12 categories. This is a free audit.',
  inputSchema: z.object({
    url: z.string().url().describe('The website URL to audit for accessibility compliance')
  }),
  async run({ args, action }) {
    const { url } = args

    try {
      // Call our Python FastAPI backend
      const response = await fetch(`${BACKEND_URL}/api/audit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Referer': 'https://hexdrive.tech'  // required for free endpoint
        },
        body: JSON.stringify({ url }),
        signal: AbortSignal.timeout(120000)  // 2 min timeout
      })

      if (!response.ok) {
        const err = await response.text()
        throw new Error(`Audit failed: ${response.status} ${err}`)
      }

      const result = await response.json() as {
        score: number
        grade: string
        url: string
        issues: Record<string, unknown>[]
        report_url?: string
        summary?: string
      }

      // Format response
      const issueCount = result.issues?.length || 0
      const reportLink = result.report_url
        ? `\n\nFull report: ${result.report_url}`
        : ''

      return `Accessibility Audit Results for ${result.url}

Score: ${result.score}/100
Grade: ${result.grade}
Issues found: ${issueCount}

${result.summary || ''}${reportLink}

Audited via Accessibility Auditor (https://hexdrive.tech) — built by a blind developer.
ENS: a11y-auditor.base.eth`

    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error)
      return `Audit error for ${url}: ${msg}. Please try again or visit https://hexdrive.tech`
    }
  }
})

// Capability 2: Get x402 payment info (for paid/detailed audits)
agent.addCapability({
  name: 'get_payment_info',
  description: 'Get payment information for the paid accessibility audit service. Returns x402 payment details including price (0.10 USDC on Base), network, and endpoint.',
  inputSchema: z.object({}),
  async run({ args, action }) {
    try {
      const response = await fetch(`${BACKEND_URL}/api/x402/info`, {
        signal: AbortSignal.timeout(10000)
      })
      const info = await response.json() as Record<string, unknown>
      return `Accessibility Auditor — x402 Payment Info

Endpoint: https://hexdrive.tech/api/audit/paid
Price: 0.10 USDC
Network: Base (eip155:84532 testnet / eip155:8453 mainnet)
Facilitator: https://x402.org/facilitator
ENS: a11y-auditor.base.eth

Full x402 info: ${JSON.stringify(info, null, 2)}`
    } catch {
      return `Accessibility Auditor — x402 Payment Info

Endpoint: https://hexdrive.tech/api/audit/paid
Price: 0.10 USDC on Base
Network: eip155:84532 (Base Sepolia testnet)
Facilitator: https://x402.org/facilitator
ENS: a11y-auditor.base.eth`
    }
  }
})

// Capability 3: Check specific accessibility category
agent.addCapability({
  name: 'check_accessibility_score',
  description: 'Quick check of a website accessibility score without full report. Faster than full audit.',
  inputSchema: z.object({
    url: z.string().url().describe('The website URL to check')
  }),
  async run({ args }) {
    const { url } = args
    try {
      const response = await fetch(`${BACKEND_URL}/api/audit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Referer': 'https://hexdrive.tech'
        },
        body: JSON.stringify({ url }),
        signal: AbortSignal.timeout(120000)
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const result = await response.json() as { score: number; grade: string; url: string }

      return `${result.url}: Score ${result.score}/100, Grade ${result.grade}`
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error)
      return `Could not check ${url}: ${msg}`
    }
  }
})

// Start agent with tunnel (works without deployment)
run(agent).then(({ stop }) => {
  console.log('Accessibility Auditor agent running on OpenServ platform')
  console.log(`Backend: ${BACKEND_URL}`)

  process.on('SIGINT', () => {
    console.log('Shutting down...')
    stop()
    process.exit(0)
  })
}).catch(err => {
  console.error('Failed to start agent:', err)
  process.exit(1)
})
