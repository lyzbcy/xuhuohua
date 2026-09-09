import { resolve, dirname } from 'path';
import { defineConfig } from 'vite';
import nodeResolve from '@rollup/plugin-node-resolve';
import { builtinModules } from 'module';
import { fileURLToPath } from 'url';
import fs from 'fs';
import { execSync } from 'child_process';
import { napcatHmrPlugin } from 'napcat-plugin-debug-cli/vite';

const __dirname = dirname(fileURLToPath(import.meta.url));

const nodeModules = [
    ...builtinModules,
    ...builtinModules.map((m) => `node:${m}`),
].flat();

const external: string[] = [];

/**
 * 递归复制目录
 */
function copyDirRecursive(src: string, dest: string) {
    if (!fs.existsSync(dest)) {
        fs.mkdirSync(dest, { recursive: true });
    }
    const entries = fs.readdirSync(src, { withFileTypes: true });
    for (const entry of entries) {
        const srcPath = resolve(src, entry.name);
        const destPath = resolve(dest, entry.name);
        if (entry.isDirectory()) {
            copyDirRecursive(srcPath, destPath);
        } else {
            fs.copyFileSync(srcPath, destPath);
        }
    }
}

/**
 * 构建后自动复制资源的 Vite 插件
 */
function copyAssetsPlugin() {
    return {
        name: 'copy-assets',
        writeBundle() {
            try {
                const distDir = resolve(__dirname, 'dist');

                // 1. 构建 WebUI 前端
                const webuiRoot = resolve(__dirname, 'src/webui');
                if (fs.existsSync(resolve(webuiRoot, 'package.json'))) {
                    try {
                        if (!fs.existsSync(resolve(webuiRoot, 'node_modules'))) {
                            console.log('[copy-assets] 正在安装 WebUI 依赖...');
                            execSync('npm install', {
                                cwd: webuiRoot,
                                stdio: 'pipe',
                            });
                        }

                        console.log('[copy-assets] 正在构建 WebUI...');
                        const webuiEnv = { ...process.env };
                        delete webuiEnv.NODE_ENV;
                        execSync('npm run build', {
                            cwd: webuiRoot,
                            stdio: 'pipe',
                            env: webuiEnv,
                        });
                        console.log('[copy-assets] WebUI 构建完成');
                    } catch (e: any) {
                        console.error('[copy-assets] WebUI 构建失败:', e.stdout?.toString().slice(-300) || e.message);
                    }

                    // 2. 复制 webui 构建产物
                    const webuiDist = resolve(__dirname, 'src/webui/dist');
                    const webuiDest = resolve(distDir, 'webui');
                    if (fs.existsSync(webuiDist)) {
                        copyDirRecursive(webuiDist, webuiDest);
                        console.log('[copy-assets] 已复制 webui 构建产物');
                    }
                }

                // 3. 生成精简的 package.json
                const pkgPath = resolve(__dirname, 'package.json');
                if (fs.existsSync(pkgPath)) {
                    const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf-8'));
                    const distPkg: Record<string, unknown> = {
                        name: pkg.name,
                        plugin: pkg.plugin,
                        version: pkg.version,
                        type: pkg.type,
                        main: pkg.main,
                        description: pkg.description,
                        author: pkg.author,
                        dependencies: pkg.dependencies,
                    };
                    if (pkg.napcat) {
                        distPkg.napcat = pkg.napcat;
                    }
                    fs.writeFileSync(
                        resolve(distDir, 'package.json'),
                        JSON.stringify(distPkg, null, 2)
                    );
                    console.log('[copy-assets] 已生成精简 package.json');
                }

                console.log('[copy-assets] 资源复制完成！');
            } catch (error) {
                console.error('[copy-assets] 资源复制失败:', error);
            }
        },
    };
}

export default defineConfig({
    resolve: {
        conditions: ['node', 'default'],
    },
    build: {
        sourcemap: false,
        target: 'esnext',
        minify: false,
        lib: {
            entry: resolve(__dirname, 'src/index.ts'),
            formats: ['es'],
            fileName: () => 'index.mjs',
        },
        rollupOptions: {
            external: [...nodeModules, ...external],
            output: {
                inlineDynamicImports: true,
            },
        },
        outDir: 'dist',
    },
    plugins: [nodeResolve(), copyAssetsPlugin(), napcatHmrPlugin({
        webui: {
            distDir: './src/webui/dist',
            targetDir: 'webui',
        },
    })],
});