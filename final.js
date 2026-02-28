const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const fs = require('fs');
const path = require('path');

// Directorios donde se guardarán los datos
const BASE_DIR = './anuncios_empleo';
const IMAGES_DIR = path.join(BASE_DIR, 'imagenes');
const JSON_DIR = path.join(BASE_DIR, 'mensajes');
const SESSION_DIR = './whatsapp_session';

// Crear directorios necesarios
function setupDirectories() {
    const dirs = [BASE_DIR, IMAGES_DIR, JSON_DIR, SESSION_DIR];
    dirs.forEach(dir => {
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
            console.log(`✅ Carpeta creada: ${dir}`);
        }
    });
}

// Crear cliente de WhatsApp con sesión persistente
const client = new Client({
    authStrategy: new LocalAuth({
        dataPath: SESSION_DIR
    }),
    puppeteer: {
        headless: false,
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--no-zygote',
            '--disable-gpu'
        ]
    }
});

// Función para generar nombre de archivo único
function generateFileName(contact, mimetype, timestamp) {
    const extension = mimetype.split('/')[1] || 'jpg';
    const safeName = contact.replace(/[^a-z0-9]/gi, '_').toLowerCase();

    return `${safeName}_${timestamp}.${extension}`;
}

// Función para generar nombre de JSON único
function generateJSONName(contact, timestamp) {
    const safeName = contact.replace(/[^a-z0-9]/gi, '_').toLowerCase();
    return `${safeName}_${timestamp}.json`;
}

// Función para guardar mensaje individual en JSON
function saveIndividualJSON(messageData, jsonFileName) {
    try {
        const jsonPath = path.join(JSON_DIR, jsonFileName);
        fs.writeFileSync(jsonPath, JSON.stringify(messageData, null, 2), 'utf-8');
        console.log(`   ✅ JSON guardado: ${jsonFileName}`);
        console.log(`   📁 Ubicación: ${path.relative(process.cwd(), jsonPath)}`);
    } catch (error) {
        console.error('   ❌ Error guardando JSON:', error.message);
    }
}

// Función principal para procesar mensajes
async function processMessage(message, eventName) {
    try {
        let contact;
        try {
            contact = await message.getContact();
        } catch (err) {
            console.log('   ⚠️ Error obteniendo contacto, usando fallback:', err.message);
            const from = message.author || message.from;
            const number = from.replace('@c.us', '').replace('@g.us', '');
            contact = {
                pushname: 'Desconocido',
                number: number,
                formattedName: `+${number}`
            };
        }
        const contactName = contact.pushname || contact.number || 'Desconocido';
        const timestamp = new Date(message.timestamp * 1000);
        const timestampNum = Date.now();
        const messageType = message.fromMe ? '📤 MENSAJE PROPIO' : '📥 MENSAJE RECIBIDO';

        console.log(`\n🔔 [${eventName}] ${messageType}`);
        console.log(`   👤 De: ${contactName}`);
        console.log(`   🕐 Hora: ${timestamp.toLocaleString()}`);
        console.log(`   💬 Texto: ${message.body || '(sin texto)'}`);
        console.log(`   📋 Tipo: ${message.type}`);
        console.log(`   📎 hasMedia: ${message.hasMedia}`);

        // Verificar si el mensaje tiene media
        const isMediaMessage = message.hasMedia ||
            message.type === 'image' ||
            message.type === 'video' ||
            message.type === 'audio' ||
            message.type === 'document';

        // Objeto para guardar en JSON
        const messageData = {
            id: message.id._serialized || message.id,
            contacto: contactName,
            numero: contact.number,
            fecha: timestamp.toISOString(),
            fechaLegible: timestamp.toLocaleString('es-ES'),
            texto: message.body || '',
            tipo: message.type,
            esPropio: message.fromMe,
            tieneMedia: message.hasMedia,
            imagenes: []
        };

        if (isMediaMessage) {
            console.log('   📥 Descargando media...');

            // Esperar si es necesario
            if (!message.hasMedia && message.type === 'image') {
                console.log('   ⏳ Esperando que el media cargue completamente...');
                await new Promise(resolve => setTimeout(resolve, 2000));
            }

            try {
                let media = null;
                let attempts = 0;
                const maxAttempts = 3;

                while (!media && attempts < maxAttempts) {
                    attempts++;
                    console.log(`   🔄 Intento ${attempts}/${maxAttempts}...`);

                    try {
                        media = await Promise.race([
                            message.downloadMedia(),
                            new Promise((_, reject) =>
                                setTimeout(() => reject(new Error('Timeout')), 15000)
                            )
                        ]);

                        if (media) break;
                    } catch (err) {
                        if (attempts < maxAttempts) {
                            console.log(`   ⏳ Esperando 2s antes del siguiente intento...`);
                            await new Promise(resolve => setTimeout(resolve, 2000));
                        }
                    }
                }

                if (!media) {
                    console.log('   ❌ No se pudo descargar el media después de varios intentos');
                    console.log('   💡 Esto puede pasar con mensajes muy recientes o conexión lenta\n');

                    // Guardar mensaje sin imagen en JSON individual
                    const jsonFileName = generateJSONName(contactName, timestampNum);
                    saveIndividualJSON(messageData, jsonFileName);
                    return;
                }

                console.log(`   ✓ Media descargado: ${media.mimetype}`);

                // Verificar si es una imagen
                if (media.mimetype.startsWith('image/')) {
                    const prefix = message.fromMe ? 'YO' : contactName.replace(/[^a-z0-9]/gi, '_');
                    const fileName = generateFileName(prefix, media.mimetype, timestampNum);
                    const filePath = path.join(IMAGES_DIR, fileName);
                    const relativePath = path.join('imagenes', fileName);

                    const buffer = Buffer.from(media.data, 'base64');
                    fs.writeFileSync(filePath, buffer);

                    // Agregar información de la imagen al objeto
                    messageData.imagenes.push({
                        nombreArchivo: fileName,
                        ruta: relativePath,
                        rutaCompleta: path.resolve(filePath),
                        mimetype: media.mimetype,
                        tamañoKB: parseFloat((buffer.length / 1024).toFixed(2))
                    });

                    console.log(`   ✅ IMAGEN GUARDADA: ${fileName}`);
                    console.log(`   📦 Tamaño: ${(buffer.length / 1024).toFixed(2)} KB`);
                    console.log(`   📁 Ubicación: ${relativePath}`);
                } else {
                    console.log(`   ℹ️  Media no es imagen: ${media.mimetype}`);
                    messageData.mediaType = media.mimetype;
                }
            } catch (downloadError) {
                console.log(`   ⚠️  Error al descargar media: ${downloadError.message}`);
                messageData.error = downloadError.message;
            }
        }

        // Guardar en JSON individual (un archivo por mensaje)
        const jsonFileName = generateJSONName(contactName, timestampNum);
        saveIndividualJSON(messageData, jsonFileName);
        console.log('');

    } catch (error) {
        console.error(`   ❌ Error procesando mensaje [${eventName}]:`, error.message);
    }
}

// Generar QR para autenticación
client.on('qr', (qr) => {
    console.log('\n🔍 ESCANEA ESTE QR CON TU TELÉFONO:\n');
    qrcode.generate(qr, { small: true });
    console.log('\n📱 Abre WhatsApp > Menú > Dispositivos vinculados\n');
});

// Autenticación exitosa
client.on('authenticated', () => {
    console.log('✅ Autenticación exitosa!');
    console.log('✅ Sesión guardada en: ./whatsapp_session/');
});

// Error de autenticación
client.on('auth_failure', (msg) => {
    console.error('❌ Error de autenticación:', msg);
    console.log('💡 SOLUCIÓN: Borra la carpeta ./whatsapp_session/ y vuelve a escanear el QR');
});

// Loading session
client.on('loading_screen', (percent, message) => {
    console.log(`⏳ Cargando: ${percent}% - ${message}`);
});

// Cliente listo
client.on('ready', async () => {
    console.log('\n✅ ¡CLIENTE DE WHATSAPP CONECTADO Y LISTO!');
    console.log(`📂 JSONs: ${path.resolve(JSON_DIR)}`);
    console.log(`📂 Imágenes: ${path.resolve(IMAGES_DIR)}`);
    console.log('👂 Escuchando mensajes de TODOS tus grupos y canales...\n');

    try {
        const chats = await client.getChats();
        const grupos = chats.filter(chat => chat.isGroup);

        console.log('\n📋 GRUPOS DISPONIBLES:');
        grupos.forEach((grupo, index) => {
            console.log(`   ${index + 1}. "${grupo.name}"`);
        });
        console.log('');
    } catch (error) {
        console.log('⚠️  No se pudieron cargar los chats');
    }

    // Listado de canales (si la versión de wwebjs lo soporta)
    try {
        if (typeof client.getChannels === 'function') {
            const canales = await client.getChannels();
            console.log('\n📢 CANALES DISPONIBLES:');
            canales.forEach((canal, index) => {
                const nombre = canal?.name || canal?.id?._serialized || `Canal ${index + 1}`;
                console.log(`   ${index + 1}. "${nombre}"`);
            });
            console.log('');
        } else {
            console.log('ℹ️ La versión de whatsapp-web.js no soporta listar canales');
        }
    } catch (error) {
        console.log('⚠️  No se pudieron cargar los canales');
    }
});

// Manejo de desconexión
client.on('disconnected', (reason) => {
    console.log('⚠️  Desconectado:', reason);
});

// Estado de cambio
client.on('change_state', state => {
    console.log('🔄 Estado cambiado a:', state);
});

// Escuchar mensajes
/* client.on('message_create', async (message) => {
    await processMessage(message, 'message_create');
}); */

// Lee todos los grupos y canales (sin listas)

// Escuchar mensajes SOLO DE GRUPOS ESPECÍFICOS
client.on('message_create', async (message) => {
    const chat = await message.getChat();

    const isGroup = chat?.isGroup === true;
    // Detección robusta de canal (propiedad nativa o sufijo del server)
    const isChannel = (chat && (chat.isChannel === true)) ||
        (chat?.id?.server === 'newsletter') ||
        (typeof chat?.id?._serialized === 'string' && chat.id._serialized.endsWith('@newsletter'));

    // Procesar todos los mensajes de grupos y canales
    if (isGroup || isChannel) {
        await processMessage(message, 'message_create');
    }
});

// Configurar directorios al inicio
setupDirectories();

// Iniciar el cliente
console.log('🚀 Iniciando WhatsApp Downloader con JSON Individual...');
console.log('\n💡 CARACTERÍSTICAS:');
console.log('   ✅ Sesión persistente en ./whatsapp_session/');
console.log('   ✅ UN JSON por cada mensaje en ./anuncios_empleo/mensajes/');
console.log('   ✅ Imágenes en ./anuncios_empleo/imagenes/');
console.log('   ✅ Detecta TODOS los mensajes (propios y externos)');
console.log('   ✅ Cada publicación tiene su propio archivo JSON');
console.log('\n⏳ Inicializando...\n');

client.initialize();

// Manejo de cierre correcto
process.on('SIGINT', async () => {
    console.log('\n🛑 Deteniendo cliente...');
    await client.destroy();
    console.log('✅ Cliente cerrado. Sesión guardada.');
    process.exit(0);
});
