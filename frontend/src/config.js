export const config = {
  region: 'ap-northeast-2',
  cognito: {
    userPoolId: 'ap-northeast-2_sGtlVpzTp',
    userPoolClientId: '40d2974cdru28vqrn6dirg1jv3',
    domain: 'whaleray-prod'
  },
  apiEndpoint: 'https://nf73cyilw6.execute-api.ap-northeast-2.amazonaws.com',
  ecrRepositoryUrl: '698928390364.dkr.ecr.ap-northeast-2.amazonaws.com/whaleray-services',
  albDns: 'whaleray-alb-403364132.ap-northeast-2.elb.amazonaws.com'
}
