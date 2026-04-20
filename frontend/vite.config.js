import { defineConfig } from 'vite'
import cesium from 'vite-plugin-cesium'
import obfuscator from 'rollup-plugin-obfuscator'

export default defineConfig({
  base: './',

  plugins: [
    cesium(),
    // 代码混淆配置
    obfuscator({
      // 限制混淆范围：只混淆我们自己写的代码，绝对不要混淆 node_modules (尤其是 Cesium)
      include: ['src/**/*.js', 'main.js'],
      
      options: {
        // 压缩代码
        compact: true,
        // 控制流扁平化：把简单的 if/else 变成复杂的 switch/case，极难阅读
        controlFlowFlattening: true,
        controlFlowFlatteningThreshold: 0.75,
        // 注入死代码：加入随机的无用逻辑干扰反编译
        deadCodeInjection: true,
        deadCodeInjectionThreshold: 0.4,
        // 调试保护：如果有人打开控制台调试，代码可能会卡死或停止运行
        debugProtection: false, // 开发时建议关掉，发布时设为 true
        debugProtectionInterval: 0,
        // 变量名混淆：变成 _0xab12 这种
        identifierNamesGenerator: 'hexadecimal',
        // 字符串加密：把 "Hello" 变成加密字符串
        stringArray: true,
        stringArrayEncoding: ['rc4'],
        stringArrayThreshold: 0.75,
        // 禁用控制台输出：上线后可以清理掉 console.log
        disableConsoleOutput: true,
      }
    })
  ],

  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000'
    }
  },
  
  build: {
    // 确保构建时清空旧文件
    emptyOutDir: true,
    // 如果想要更小的体积，可以调高 target
    target: 'es2015'
  }
})