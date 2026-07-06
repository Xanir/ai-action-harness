const { spawn } = require('child_process');

// Grab arguments passed from PM2 and re-quote any that contain spaces.
// This prevents the Windows shell from fracturing the command.
const args = process.argv.slice(2).map(arg => {
    return arg.includes(' ') ? `"${arg}"` : arg;
});

const isWin = process.platform === 'win32';

const mcp = spawn(isWin ? 'npx.cmd' : 'npx', args, {
    stdio: 'inherit',
    windowsHide: true,
    shell: isWin       
});

mcp.on('error', (err) => {
    console.error('Failed to start subprocess:', err);
    process.exit(1);
});

mcp.on('close', (code) => {
    process.exit(code);
});