const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const express = require('express');
const axios = require('axios');

const app = express();
app.use(express.json({ limit: '50mb' }));

const PORT = 3000;
const API_URL = process.env.API_URL || 'http://api:5000';

const client = new Client({
    authStrategy: new LocalAuth(),
    puppeteer: {
        executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || null,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
    }
});

client.on('qr', (qr) => {
    qrcode.generate(qr, { small: true });
    console.log('Scan the QR code above to log in to WhatsApp Web.');
});

client.on('ready', () => {
    console.log('WhatsApp Client is ready!');
});

client.on('message', async msg => {
    console.log('Received message:', msg.body, 'from', msg.from);
    if (msg.from.endsWith('@g.us')) {
        return;
    }
    let type = msg.type || 'text';
    let mediaData = null;
    let mimeType = null;
    let filename = null;

    if (msg.hasMedia) {
        try {
            const media = await msg.downloadMedia();
            if (media) {
                if (media.mimetype.startsWith('image/')) type = 'image';
                else if (media.mimetype.startsWith('video/')) type = 'video';
                else if (media.mimetype.startsWith('audio/')) type = 'audio';
                else type = 'document';

                mediaData = media.data; // Base64
                mimeType = media.mimetype;
                filename = media.filename;
            }
        } catch (e) {
            console.error('Failed to download media for msg', msg.id.id, e);
        }
    }

    try {
        const headers = {};
        if (process.env.CLF_SERVICE_TOKEN_CLIENT_ID && process.env.CLF_SERVICE_TOKEN_CLIENT_SECRET) {
            headers['CF-Access-Client-Id'] = process.env.CLF_SERVICE_TOKEN_CLIENT_ID.replace(/^["']|["']$/g, '');
            headers['CF-Access-Client-Secret'] = process.env.CLF_SERVICE_TOKEN_CLIENT_SECRET.replace(/^["']|["']$/g, '');
        }

        await axios.post(`${API_URL}/incoming-whatsapp`, {
            from: msg.from,
            body: msg.body,
            type: type,
            media_data: mediaData,
            media_mime_type: mimeType,
            media_filename: filename,
            timestamp: msg.timestamp
        }, { headers });
        console.log('Message forwarded to API successfully.');
    } catch (error) {
        console.error('Failed to forward message to API:', error.message);
        if (error.response) {
            console.error('Response data:', error.response.data);
            console.error('Response status:', error.response.status);
        }
    }
});

app.post('/send', async (req, res) => {
    const { cellphone, message, type = 'text', media_data, media_mime_type, media_filename } = req.body;
    if (!cellphone) {
        return res.status(400).json({ error: 'cellphone is required' });
    }

    try {
        let number = cellphone.replace(/[^0-9]/g, '');
        if (!number.endsWith('@c.us')) {
            number = `${number}@c.us`;
        }

        const { MessageMedia } = require('whatsapp-web.js');
        let options = {};
        let content = message || '';

        if (type !== 'text' && media_data) {
            content = new MessageMedia(media_mime_type || 'application/octet-stream', media_data, media_filename);
            options.caption = message || '';
        }

        const response = await client.sendMessage(number, content, options);
        console.log('Message sent successfully:', response.id.id);

        return res.status(200).json({
            status: 'SENT',
            message_code: response.id.id
        });
    } catch (error) {
        console.error('Failed to send message:', error);
        return res.status(500).json({ status: 'FAILED', error: error.message });
    }
});

app.listen(PORT, '0.0.0.0', () => {
    console.log(`WhatsApp JS Worker listening on port ${PORT}`);
    client.initialize();
});
