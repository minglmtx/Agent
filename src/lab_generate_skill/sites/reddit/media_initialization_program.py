"""Exact shipped filesystem factory, without kernel, SQL, HTTP or image upload."""

INITIALIZE_MEDIA = r"""
$pins=[
 '/var/www/html/src/Storage/DsnAwareFilesystemFactory.php'=>'2e531b5f3b20a31d7b933b175d8a3519992ae13fc9dd937761fbaefb6cfe2bc6',
 '/var/www/html/vendor/league/flysystem/src/Adapter/Local.php'=>'462d0ed21f5e4d0f7c76cd402375655741af638d8bd760e7307a0481726dd991',
 '/var/www/html/config/packages/flysystem.yaml'=>'f07d088abc00610fa5954659c7852ae215fb20d26b8cec98f19dabbfae02af08'];
foreach($pins as $path=>$sha){
 if(is_link($path)||!is_file($path)||hash_file('sha256',$path)!==$sha)throw new RuntimeException('Original storage source differs');
}
$env='/state/app.env';$s=lstat($env);
if(!$s||is_link($env)||!is_file($env)||$s['nlink']!==1||$s['size']>65536)throw new RuntimeException('Private configured environment required');
$raw=file_get_contents($env);
if(preg_match_all('/^UPLOAD_DSN=[^\r\n]*$/m',$raw)!==1||preg_match('/^UPLOAD_DSN="file:\/\/\/state\/media-native"\r?$/m',$raw)!==1)throw new RuntimeException('Original native upload location required');
$root='/state/media-native';
if(is_link($root)||!is_dir($root)||array_values(array_diff(scandir($root),['.','..']))!==[])throw new RuntimeException('Fresh empty native media required');
require '/var/www/html/vendor/autoload.php';
$storage=\App\Storage\DsnAwareFilesystemFactory::createFilesystem('file:///state/media-native',['prefix'=>'submission_images/','visibility'=>'public']);
clearstatcache();$target=$root.'/submission_images';
if(array_values(array_diff(scandir($root),['.','..']))!==['submission_images']||is_link($target)||!is_dir($target)||array_values(array_diff(scandir($target),['.','..']))!==[])throw new RuntimeException('Native constructor changed unexpected media');
echo 'native-storage-initialized/1';
"""
