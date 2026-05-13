import { useState, useEffect } from 'react'
import { Copy, CheckCircle2, AlertCircle, Wallet, Clock, Shield } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'

interface BillingData {
  subscription: {
    tier: string
    active: boolean
    expires_at: string | null
  }
  payment_instructions: {
    address: string
    memo: string
    xrp_amount: string
    rlusd_amount: string
    instructions: string
  }
  pricing: {
    monthly_xrp: number
    monthly_rlusd: number
  }
}

function formatAddress(addr: string) {
  return `${addr.slice(0, 8)}...${addr.slice(-8)}`
}

export default function Billing() {
  const [data, setData] = useState<BillingData | null>(null)
  const [loading, setLoading] = useState(true)
  const [, setError] = useState('')
  const [copied, setCopied] = useState<string | null>(null)
  const { token } = useAuthStore()

  useEffect(() => {
    if (!token) return
    fetch('/api/billing', {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => {
        if (r.status === 403) {
          setData({
            subscription: { tier: 'free', active: false, expires_at: null },
            payment_instructions: {
              address: '',
              memo: '',
              xrp_amount: '25',
              rlusd_amount: '25',
              instructions: '',
            },
            pricing: { monthly_xrp: 25, monthly_rlusd: 25 },
          })
          return null
        }
        if (!r.ok) throw new Error('Failed to load billing')
        return r.json()
      })
      .then((d) => {
        if (d) setData(d)
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [token])

  const copy = (text: string, label: string) => {
    navigator.clipboard.writeText(text)
    setCopied(label)
    setTimeout(() => setCopied(null), 2000)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  const sub = data?.subscription
  const inst = data?.payment_instructions
  const isActive = sub?.active && sub?.expires_at && new Date(sub.expires_at) > new Date()

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-white">Billing</h1>
        <p className="text-sm text-gray-500 mt-1">Manage your subscription and payments</p>
      </div>

      {/* Subscription Status */}
      <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${isActive ? 'bg-green-500/10' : 'bg-red-500/10'}`}>
              <Shield className={`w-5 h-5 ${isActive ? 'text-green-400' : 'text-red-400'}`} />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">
                {isActive ? 'Active Subscription' : 'No Active Subscription'}
              </h2>
              <p className="text-sm text-gray-500">
                {isActive
                  ? `Tier: ${sub?.tier} · Expires: ${sub?.expires_at ? new Date(sub.expires_at).toLocaleDateString() : 'N/A'}`
                  : 'Subscribe to access trading features'}
              </p>
            </div>
          </div>
          {isActive && (
            <span className="px-3 py-1 rounded-full bg-green-500/10 text-green-400 text-xs font-medium border border-green-500/20">
              Active
            </span>
          )}
        </div>

        {!isActive && (
          <div className="bg-red-500/5 border border-red-500/20 rounded-xl p-4 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm text-red-400 font-medium">Subscription Required</p>
              <p className="text-xs text-gray-500 mt-1">
                Your subscription has expired or you are on the free tier. Purchase a plan below to resume trading.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Payment Instructions */}
      <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-orange-500/10 flex items-center justify-center">
            <Wallet className="w-5 h-5 text-orange-400" />
          </div>
          <h2 className="text-lg font-semibold text-white">Pay with Crypto</h2>
        </div>

        <div className="space-y-4">
          {/* XRP Payment */}
          <div className="bg-[#0a0a0f] rounded-xl p-5 border border-[#2a2a35]">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-white">XRP</span>
                <span className="text-xs text-gray-500">{data?.pricing.monthly_xrp} XRP / month</span>
              </div>
              <span className="text-xs text-gray-600">Ripple Network</span>
            </div>

            {inst?.address && (
              <>
                <div className="space-y-2">
                  <div className="flex items-center justify-between bg-[#16161f] rounded-lg px-3 py-2 border border-[#2a2a35]">
                    <div>
                      <p className="text-[10px] text-gray-500 uppercase tracking-wider">Address</p>
                      <code className="text-xs text-gray-300 font-mono">{formatAddress(inst.address)}</code>
                    </div>
                    <button
                      onClick={() => copy(inst.address, 'addr')}
                      className="p-1.5 rounded-md hover:bg-white/5 text-gray-500 hover:text-orange-400 transition-colors"
                    >
                      {copied === 'addr' ? <CheckCircle2 className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
                    </button>
                  </div>

                  <div className="flex items-center justify-between bg-[#16161f] rounded-lg px-3 py-2 border border-[#2a2a35]">
                    <div>
                      <p className="text-[10px] text-gray-500 uppercase tracking-wider">Memo (Required)</p>
                      <code className="text-xs text-orange-300 font-mono font-bold">{inst.memo}</code>
                    </div>
                    <button
                      onClick={() => copy(inst.memo, 'memo')}
                      className="p-1.5 rounded-md hover:bg-white/5 text-gray-500 hover:text-orange-400 transition-colors"
                    >
                      {copied === 'memo' ? <CheckCircle2 className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                <div className="mt-3 bg-yellow-500/5 border border-yellow-500/20 rounded-lg p-3">
                  <p className="text-xs text-yellow-400/80">
                    <strong>Important:</strong> Include your username <code className="text-orange-300">{inst.memo}</code> in the memo field.
                    Without it, we cannot credit your account.
                  </p>
                </div>
              </>
            )}
          </div>

          {/* RLUSD Payment */}
          <div className="bg-[#0a0a0f] rounded-xl p-5 border border-[#2a2a35]">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-white">RLUSD</span>
                <span className="text-xs text-gray-500">{data?.pricing.monthly_rlusd} RLUSD / month</span>
              </div>
              <span className="text-xs text-gray-600">Ripple USD Stablecoin</span>
            </div>
            <p className="text-xs text-gray-500">
              Send RLUSD to the same address above. Include your username in the memo.
            </p>
          </div>
        </div>
      </div>

      {/* How It Works */}
      <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-6">
        <h2 className="text-lg font-semibold text-white mb-4">How It Works</h2>
        <div className="space-y-3">
          {[
            { icon: Wallet, text: 'Send XRP or RLUSD to the address above' },
            { icon: Copy, text: 'Include your username in the transaction memo' },
            { icon: Clock, text: 'We verify the payment on the XRP Ledger (~1 min)' },
            { icon: CheckCircle2, text: 'Your subscription activates automatically' },
          ].map((step, i) => (
            <div key={i} className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-[#0a0a0f] border border-[#2a2a35] flex items-center justify-center">
                <step.icon className="w-4 h-4 text-gray-400" />
              </div>
              <span className="text-sm text-gray-400">{step.text}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
