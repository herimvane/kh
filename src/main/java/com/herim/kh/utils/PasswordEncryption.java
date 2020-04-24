package com.herim.kh.utils;

import org.apache.shiro.crypto.hash.SimpleHash;
import org.apache.shiro.util.ByteSource;

/**
 * 密码加密
 * @author herimvane
 *
 */
public class PasswordEncryption {
	
	public static String encrypt(String password,String salt) {
		return new SimpleHash("MD5", password, ByteSource.Util.bytes(salt), 2).toHex();
	}

}
