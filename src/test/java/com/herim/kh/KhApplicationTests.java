package com.herim.kh;

import org.apache.shiro.crypto.hash.SimpleHash;
import org.apache.shiro.util.ByteSource;
import org.junit.jupiter.api.Test;

class KhApplicationTests {
	
	

	@Test
	void contextLoads() throws Exception {
		
		String hashAlgorithmName = "MD5";
        //加密次数
        int hashInteractions = 2;
        //盐值
        String salt = "HERIMVANE";
        //原密码
        String pwd = "12345678";
        //将得到的result放到数据库中就行了。
        String result = new SimpleHash(hashAlgorithmName, pwd, ByteSource.Util.bytes(salt), hashInteractions).toHex();
        System.out.println(result);
        System.out.println((double)Math.round(90.24171428571428*100)/100);
	}
	

}
