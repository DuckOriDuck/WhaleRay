import { Amplify } from 'aws-amplify'
import { config } from '../config'

export const configureAuth = () => {
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: config.cognito.userPoolId,
        userPoolClientId: config.cognito.userPoolClientId,
        loginWith: {
          oauth: {
            domain: `${config.cognito.domain}.auth.${config.region}.amazoncognito.com`,
            scopes: ['openid', 'email', 'profile'],
            redirectSignIn: [window.location.origin],
            redirectSignOut: [window.location.origin],
            responseType: 'code'
          }
        }
      }
    }
  })
}
