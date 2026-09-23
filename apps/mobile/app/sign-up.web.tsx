import { SignUp } from '@clerk/expo/web';
import { Redirect } from 'expo-router';
import { ActivityIndicator } from 'react-native';
import { Brand, Footer, Screen } from '../src/components/ui';
import { useSession } from '../src/features/auth/session';
export default function SignUpPage() {
 const { ready, signedIn } = useSession();
 if (!ready) return <Screen><ActivityIndicator /></Screen>;
 if (signedIn) return <Redirect href="/home" />;
 return <Screen><Brand /><SignUp routing="hash" signInUrl="/" forceRedirectUrl="/home"
   appearance={{ variables: { fontFamily: 'system-ui, sans-serif', colorPrimary: '#0f92ac', borderRadius: '1.5rem' },
     elements: { rootBox: { width: '100%' }, cardBox: { width: '100%' } } }} /><Footer /></Screen>;
}
