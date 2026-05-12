import { ConnectButton } from '@rainbow-me/rainbowkit'
import { useAccount, useBalance } from 'wagmi'
import { Wallet, Copy, ExternalLink, AlertCircle, CheckCircle2 } from 'lucide-react'
import { useState } from 'react'

function formatAddress(addr: string) {
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`
}

export default function WalletPage() {
  const { address, isConnected, chain } = useAccount()
  const { data: balance } = useBalance({ address })
  const [copied, setCopied] = useState(false)

  const copyAddress = () => {
    if (!address) return
    navigator.clipboard.writeText(address)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Wallet</h1>
          <p className="text-sm text-gray-500 mt-1">Connect your crypto wallet to fund your trading account</p>
        </div>
        <ConnectButton />
      </div>

      {!isConnected ? (
        <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-12 text-center">
          <div className="w-16 h-16 rounded-2xl bg-orange-500/10 flex items-center justify-center mx-auto mb-4">
            <Wallet className="w-8 h-8 text-orange-400" />
          </div>
          <h2 className="text-lg font-semibold text-white mb-2">Connect Your Wallet</h2>
          <p className="text-sm text-gray-500 mb-6 max-w-md mx-auto">
            Link your Web3 wallet to deposit crypto and fund your HedgeSwarm trading account.
            We support MetaMask, WalletConnect, Coinbase Wallet, and more.
          </p>
          <ConnectButton />
        </div>
      ) : (
        <>
          {/* Wallet Info Card */}
          <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-semibold text-white">Connected Wallet</h2>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                <span className="text-xs text-green-400 font-medium">Connected</span>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-[#0a0a0f] rounded-xl p-4 border border-[#2a2a35]">
                <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Address</p>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-white font-mono">{formatAddress(address!)}</span>
                  <button
                    onClick={copyAddress}
                    className="p-1 rounded-lg hover:bg-white/5 text-gray-500 hover:text-orange-400 transition-colors"
                    title="Copy address"
                  >
                    {copied ? <CheckCircle2 className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <div className="bg-[#0a0a0f] rounded-xl p-4 border border-[#2a2a35]">
                <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Network</p>
                <p className="text-sm text-white">{chain?.name || 'Unknown'}</p>
              </div>

              <div className="bg-[#0a0a0f] rounded-xl p-4 border border-[#2a2a35]">
                <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Balance</p>
                <p className="text-sm text-white">
                  {balance ? `${parseFloat(balance.formatted).toFixed(4)} ${balance.symbol}` : 'Loading...'}
                </p>
              </div>
            </div>
          </div>

          {/* Fund Account Section */}
          <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-6">
            <h2 className="text-lg font-semibold text-white mb-4">Fund Your Trading Account</h2>

            <div className="space-y-4">
              <div className="bg-[#0a0a0f] rounded-xl p-5 border border-[#2a2a35]">
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-xl bg-orange-500/10 flex items-center justify-center flex-shrink-0">
                    <Wallet className="w-5 h-5 text-orange-400" />
                  </div>
                  <div className="flex-1">
                    <h3 className="text-sm font-semibold text-white mb-1">Deposit Address</h3>
                    <p className="text-xs text-gray-500 mb-3">
                      Send USDT (ERC-20) or ETH to this address. Deposits are credited to your paper trading balance for testing.
                    </p>
                    <div className="flex items-center gap-2 bg-[#16161f] rounded-lg px-3 py-2 border border-[#2a2a35]">
                      <code className="text-xs text-gray-300 font-mono flex-1 truncate">{address}</code>
                      <button
                        onClick={copyAddress}
                        className="p-1.5 rounded-md hover:bg-white/5 text-gray-500 hover:text-orange-400 transition-colors"
                      >
                        {copied ? <CheckCircle2 className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              <div className="bg-[#0a0a0f] rounded-xl p-5 border border-[#2a2a35]">
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-xl bg-blue-500/10 flex items-center justify-center flex-shrink-0">
                    <ExternalLink className="w-5 h-5 text-blue-400" />
                  </div>
                  <div className="flex-1">
                    <h3 className="text-sm font-semibold text-white mb-1">View on Explorer</h3>
                    <p className="text-xs text-gray-500 mb-3">
                      Check your wallet transactions and balance on the blockchain explorer.
                    </p>
                    <a
                      href={`${chain?.blockExplorers?.default?.url || 'https://etherscan.io'}/address/${address}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 text-xs text-orange-400 hover:text-orange-300 transition-colors"
                    >
                      <ExternalLink className="w-3 h-3" />
                      Open Explorer
                    </a>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Security Notice */}
          <div className="bg-yellow-500/5 border border-yellow-500/20 rounded-xl p-4 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm text-yellow-400 font-medium">Security Notice</p>
              <p className="text-xs text-gray-500 mt-1">
                HedgeSwarm never stores your private keys. Wallet connection is read-only.
                Always verify deposit addresses before sending funds.
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
