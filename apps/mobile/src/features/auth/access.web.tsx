import { SignIn } from '@clerk/expo/web';
export default function Access() {
 return <SignIn routing="hash" signUpUrl="/sign-up" forceRedirectUrl="/home" signUpForceRedirectUrl="/home"
   appearance={{ variables: { fontFamily: 'system-ui, sans-serif', colorPrimary: '#0f92ac', borderRadius: '1.5rem' },
     elements: { rootBox: { width: '100%' }, cardBox: { width: '100%' } } }} />;
}
