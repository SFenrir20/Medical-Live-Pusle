import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import Login from '../../app/index';
import ForgotPassword from '../../app/forgot-password';
import Home from '../../app/home';
import { SessionProvider } from '../features/auth/session';

jest.mock('@react-native-async-storage/async-storage', () => require('@react-native-async-storage/async-storage/jest/async-storage-mock'));
jest.mock('expo-router', () => {
  const { Text } = require('react-native');
  return ({
  Link: ({ children }: { children: React.ReactNode }) => <Text>{children}</Text>,
  Redirect: ({ href }: { href: string }) => <Text>redirect:{href}</Text>,
}); });
jest.mock('react-native-safe-area-context', () => ({ SafeAreaView: require('react-native').View }));

beforeEach(async () => { await AsyncStorage.clear(); jest.clearAllMocks(); });

test('valida correo y rechaza credenciales incorrectas', async () => {
  render(<SessionProvider><Login /></SessionProvider>);
  await screen.findByText('Bienvenida');
  fireEvent.press(screen.getByText('INICIAR SESIÓN'));
  expect(screen.getByText('Ingresa un correo electrónico válido.')).toBeTruthy();
  fireEvent.changeText(screen.getByLabelText('Correo electrónico'), 'andrea@livepulse.com');
  fireEvent.changeText(screen.getByLabelText('Contraseña'), 'incorrecta');
  fireEvent.press(screen.getByText('INICIAR SESIÓN'));
  await screen.findByText('Correo o contraseña incorrectos. Usa el acceso de demostración.');
  expect(AsyncStorage.setItem).not.toHaveBeenCalled();
});

test('recuerda solo un marcador demo y nunca la contraseña', async () => {
  render(<SessionProvider><Login /></SessionProvider>);
  await screen.findByText('Bienvenida');
  fireEvent.changeText(screen.getByLabelText('Correo electrónico'), 'andrea@livepulse.com');
  fireEvent.changeText(screen.getByLabelText('Contraseña'), '123456');
  fireEvent.press(screen.getByText('INICIAR SESIÓN'));
  await screen.findByText('redirect:/home');
  expect(AsyncStorage.setItem).toHaveBeenCalledWith('livepulse.preview-session.v1', 'demo');
});

test('la recuperación demo no afirma que envió correo', () => {
  render(<ForgotPassword />);
  fireEvent.changeText(screen.getByLabelText('Correo electrónico'), 'andrea@livepulse.com');
  fireEvent.press(screen.getByText('PROBAR RECUPERACIÓN'));
  expect(screen.getByText(/No se ha enviado ningún correo/)).toBeTruthy();
});

test('protege la jornada cuando no hay sesión', async () => {
  render(<SessionProvider><Home /></SessionProvider>);
  await screen.findByText('redirect:/');
});

test('restaura demo, selecciona segunda cuenta y no confirma turnos reales', async () => {
  await AsyncStorage.setItem('livepulse.preview-session.v1', 'demo');
  render(<SessionProvider><Home /></SessionProvider>);
  await screen.findByText('Hola, Andrea 👋');
  fireEvent.press(screen.getByLabelText('@medical.cirugias2'));
  expect(screen.getByText('Cuenta seleccionada: @medical.cirugias2')).toBeTruthy();
  fireEvent.press(screen.getByText('MARCAR INICIO'));
  expect(screen.getByText(/No se ha registrado una entrada/)).toBeTruthy();
  fireEvent.press(screen.getByText('Cerrar sesión'));
  await screen.findByText('redirect:/');
  await waitFor(() => expect(AsyncStorage.removeItem).toHaveBeenCalledWith('livepulse.preview-session.v1'));
});
