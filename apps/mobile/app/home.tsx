import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { Redirect } from 'expo-router';
import { Button, Card, ErrorText, Footer, Screen, s } from '../src/components/ui';
import { useSession } from '../src/features/auth/session';
import { accounts } from '../src/features/accounts';
import { getProfile, Profile } from '../src/services/api';
import { theme } from '../src/theme';
import { ShiftCard } from '../src/features/shifts/ShiftCard';

export default function Home() {
  const { ready, signedIn, logout, getToken, name } = useSession();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!ready || !signedIn) return;
    let active = true;
    getToken().then(getProfile)
      .then(value => { if (active) setProfile(value); })
      .catch(() => {
        if (active) setError('No se pudieron cargar las cuentas de TikTok. Inténtalo otra vez.');
      });
    return () => { active = false; };
  }, [ready, signedIn, getToken, attempt]);

  function reloadAccounts() {
    setError('');
    setProfile(null);
    setSelectedAccountId(null);
    setAttempt(value => value + 1);
  }

  if (!ready) return <Screen><ActivityIndicator /></Screen>;
  if (!signedIn) return <Redirect href="/" />;

  const availableAccounts = profile?.status === 'approved'
    ? accounts.filter(account => profile.accounts.includes(account.id)) : [];
  const selectedAccount = availableAccounts.find(account => account.id === selectedAccountId);

  return (
    <Screen>
      <View style={s.row}>
        <Text style={s.heading}>LivePulse</Text>
        <Pressable accessibilityRole="button" onPress={() => {
          void logout().catch(() => setError('No se pudo cerrar la sesión.'));
        }}>
          <Text style={s.link}>Cerrar sesión</Text>
        </Pressable>
      </View>
      <Text style={s.title}>Hola, {name}</Text>
      <ErrorText message={error} />
      {!!error && <Button title="REINTENTAR" onPress={reloadAccounts} />}
      {!profile && !error && <ActivityIndicator accessibilityLabel="Cargando cuentas" />}

      {profile && availableAccounts.length === 0 && (
        <Card>
          <Text style={s.heading}>No hay cuentas disponibles</Text>
          <Text style={s.subtitle}>No tienes cuentas de TikTok disponibles para seleccionar. Puedes actualizar la lista o contactar al responsable de LivePulse.</Text>
          <Button title="ACTUALIZAR CUENTAS" onPress={reloadAccounts} />
        </Card>
      )}

      {availableAccounts.length > 0 && (
        <>
          <Card>
            <Text style={s.heading}>¿En qué cuenta harás el LIVE?</Text>
            <Text style={s.subtitle}>Elige la cuenta de TikTok que vas a utilizar.</Text>
            <View accessibilityRole="radiogroup" accessibilityLabel="Cuenta de TikTok">
              {availableAccounts.map(account => {
                const selected = selectedAccount?.id === account.id;
                return (
                  <Pressable
                    key={account.id}
                    accessibilityRole="radio"
                    accessibilityLabel={account.handle}
                    accessibilityState={{ checked: selected }}
                    onPress={() => setSelectedAccountId(account.id)}
                    style={({ pressed }) => [styles.account, selected && styles.selected, pressed && styles.pressed]}
                  >
                    <View style={[styles.radio, selected && styles.radioSelected]}>
                      {selected && <View style={styles.dot} />}
                    </View>
                    <View style={styles.accountText}>
                      <Text style={styles.handle}>{account.handle}</Text>
                      <Text style={s.subtitle}>{selected ? 'Seleccionada' : 'Toca para elegir'}</Text>
                    </View>
                  </Pressable>
                );
              })}
            </View>
          </Card>
          {selectedAccount && (
            <ShiftCard key={selectedAccount.id} accountId={selectedAccount.id}
              userId={profile!.id} getToken={getToken} />
          )}
        </>
      )}
      <Footer />
    </Screen>
  );
}

const styles = StyleSheet.create({
  account: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    padding: 16, marginTop: 14, borderRadius: 18,
    borderWidth: 1, borderColor: theme.colors.border,
  },
  selected: { borderColor: theme.colors.primary, backgroundColor: theme.colors.pale },
  pressed: { opacity: 0.75 },
  accountText: { flex: 1 },
  handle: { color: theme.colors.ink, fontSize: 16, fontWeight: '600' },
  radio: {
    width: 24, height: 24, borderRadius: 12, borderWidth: 2,
    borderColor: theme.colors.muted, alignItems: 'center', justifyContent: 'center',
  },
  radioSelected: { borderColor: theme.colors.primary },
  dot: { width: 12, height: 12, borderRadius: 6, backgroundColor: theme.colors.primary },
  explanation: { marginTop: 12 },
});
