export const config = {
  region: import.meta.env.VITE_REGION || 'ap-northeast-2',
  apiEndpoint: import.meta.env.VITE_API_ENDPOINT || 'https://api.whaleray.oriduckduck.site',
  authEndpoint: import.meta.env.VITE_AUTH_ENDPOINT || 'https://api.whaleray.oriduckduck.site/auth/github',
  frontendUrl: import.meta.env.VITE_FRONTEND_URL || 'https://whaleray.oriduckduck.site',
  githubAppHomepage: import.meta.env.VITE_GITHUB_APP_HOMEPAGE || 'https://github.com/apps/whaleray',
  githubAppInstallUrl: import.meta.env.VITE_GITHUB_APP_INSTALL_URL || 'https://github.com/apps/whaleray/installations/select_target',
  githubAppSetupUrl: import.meta.env.VITE_GITHUB_APP_SETUP_URL || 'https://app.whaleray.oriduckduck.site/setup',
  ecrRepositoryUrl: import.meta.env.VITE_ECR_REPOSITORY_URL || '698928390364.dkr.ecr.ap-northeast-2.amazonaws.com/whaleray-services',
  albDns: import.meta.env.VITE_ALB_DNS || 'whaleray-alb-403364132.ap-northeast-2.elb.amazonaws.com'
}
