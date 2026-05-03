/** @type {import('next').NextConfig} */
const nextConfig = {
    trailingSlash: true,
    eslint: {
        ignoreDuringBuilds: false,
    },
    typescript: {
        ignoreBuildErrors: false,
    },
    images: {
        unoptimized: true,
    },
};

export default nextConfig;
