import { getDefaultConfig } from '@rainbow-me/rainbowkit'
import { mainnet, polygon, optimism, arbitrum, base } from 'wagmi/chains'

export const config = getDefaultConfig({
  appName: 'HedgeSwarm',
  projectId: 'hedgeswarm-wallet', // WalletConnect project ID (free at cloud.walletconnect.com)
  chains: [mainnet, polygon, optimism, arbitrum, base],
  ssr: false,
})
