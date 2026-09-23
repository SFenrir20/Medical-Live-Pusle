import { ActivityIndicator } from 'react-native';
import { Redirect } from 'expo-router';
import { Brand, Footer, Screen } from '../src/components/ui';
import { useSession } from '../src/features/auth/session';
import Access from '../src/features/auth/access';
export default function Login() {
 const { ready, signedIn } = useSession();
 if (!ready) return <Screen><ActivityIndicator /></Screen>;
 if (signedIn) return <Redirect href="/home" />;
 return <Screen><Brand /><Access /><Footer /></Screen>;
}
